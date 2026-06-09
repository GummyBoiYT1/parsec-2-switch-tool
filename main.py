from struct import pack
import socket
import threading
import tkinter as tk
from tkinter import messagebox, ttk
from time import sleep, time
import os 
import pygame 

"""
taken alot of stuff from sys-hidplus's python folder and restructured it into a more user-friendly GUI 
for parsec users to easily connect their PC gamepads to the switch 
without needing to mess with command line tools or other stff
"""

class SwitchConnection:
    MAGIC_NUMBER = 0x3276
    PACKET_FORMAT = "<HHHQiiiiHQiiiiHQiiiiHQiiiiHQiiiiHQiiiiHQiiiiHQiiii"

    def __init__(self, switch_ip=None, port=8000):
        self.switch_ip = switch_ip
        self.port = port
        self.server_address = (self.switch_ip, self.port) if switch_ip else None
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        
        self.slots = {i: {"type": 0, "buttons": 0, "lx": 0, "ly": 0, "rx": 0, "ry": 0} for i in range(1, 9)}
        
        self.is_running = False
        self.heartbeat_thread = None
        self.active_count = 4 

    def start(self, switch_ip, active_count=4):
        self.switch_ip = switch_ip
        self.active_count = active_count
        self.server_address = (self.switch_ip, self.port)
        if not self.is_running:
            self.is_running = True
            self.heartbeat_thread = threading.Thread(target=self._network_loop, daemon=True)
            self.heartbeat_thread.start()

    def stop(self):
        self.is_running = False
        if self.heartbeat_thread:
            self.heartbeat_thread.join()
        for slot in self.slots.values():
            self._reset_slot_data(slot)
        self._send_packet()

    def update_slot(self, player_number, con_type, buttons, lx, ly, rx, ry):
        if player_number in self.slots:
            self.slots[player_number] = {
                "type": con_type, "buttons": buttons,
                "lx": lx, "ly": ly, "rx": rx, "ry": ry
            }

    def disconnect_slot(self, player_number):
        if player_number in self.slots:
            self._reset_slot_data(self.slots[player_number])

    def _reset_slot_data(self, slot_dict):
        slot_dict.update({"type": 0, "buttons": 0, "lx": 0, "ly": 0, "rx": 0, "ry": 0})

    def _network_loop(self):
        while self.is_running:
            start_time = time()
            self._send_packet()
            elapsed = time() - start_time
            sleep(max(0, (1 / 60.0) - elapsed))

    def _send_packet(self):
        if not self.server_address: return
        
        # tell sys-hidplus how many controllers to look for
        packet_data = [self.MAGIC_NUMBER, self.active_count]
        
        for p_id in sorted(self.slots.keys()):
            s = self.slots[p_id]
            packet_data.extend([s["type"], s["buttons"], s["lx"], s["ly"], s["rx"], s["ry"]])
            
        try:
            packet = pack(self.PACKET_FORMAT, *packet_data)
            self.sock.sendto(packet, self.server_address)
        except:
            pass

class VirtualController:
    BUTTONS = {
        "A": 1, "B": 1 << 1, "X": 1 << 2, "Y": 1 << 3,
        "LST": 1 << 4, "RST": 1 << 5, "L": 1 << 6, "R": 1 << 7,
        "ZL": 1 << 8, "ZR": 1 << 9, "PLUS": 1 << 10, "MINUS": 1 << 11,
        "DL": 1 << 12, "DU": 1 << 13, "DR": 1 << 14, "DD": 1 << 15
    }
    TYPE_PRO = 1

    def __init__(self, connection_manager, player_number):
        self.manager = connection_manager
        self.player_number = player_number
        self.is_active = False
        self.buttons_state = 0
        self.lx, self.ly, self.rx, self.ry = 0, 0, 0, 0

    def activate(self):
        self.is_active = True
        self._push()

    def _push(self):
        if self.is_active:
            self.manager.update_slot(
                self.player_number, self.TYPE_PRO, self.buttons_state,
                self.lx, self.ly, self.rx, self.ry
            )

    def change_player_slot(self, new_player_number):
        if self.player_number == new_player_number: return
        self.manager.disconnect_slot(self.player_number)
        self.player_number = new_player_number
        self._push()

    def set_button_by_bitmask(self, bitmask, pressed=True):
        if pressed:
            self.buttons_state |= bitmask
        else:
            self.buttons_state &= ~bitmask
        self._push()

    def set_sticks(self, lx=0, ly=0, rx=0, ry=0):
        self.lx, self.ly, self.rx, self.ry = int(lx), int(ly), int(rx), int(ry)
        self._push()

    def blue_screen_clear(self):
        self.buttons_state = 0
        self.lx, self.ly, self.rx, self.ry = 0, 0, 0, 0
        self._push()

    def disconnect(self):
        self.is_active = False
        self.manager.disconnect_slot(self.player_number)


class SmashParsecGUI:
    PYGAME_BUTTON_MAP = {
        0: 1,       # A (Xbox A)
        1: 1 << 1,  # B (Xbox B)
        2: 1 << 2,  # X (Xbox X)
        3: 1 << 3,  # Y (Xbox Y)
        4: 1 << 11, # MINUS (Xbox Share/Select)
        6: 1 << 10, # PLUS (Xbox Menu/Start)
        7: 1 << 4,  # LST
        8: 1 << 5,  # RST
        9: 1 << 6,  # L
        10: 1 << 7, # R
    }

    KEYBOARD_MAP = {
        'j': 1,         # A
        'k': 1 << 1,    # B
        'u': 1 << 2,    # X
        'i': 1 << 3,    # Y
        'q': 1 << 11,   # MINUS
        'e': 1 << 10,   # PLUS
        'Up': 1 << 13,  # D-Pad Up    
        'Down': 1 << 15,# D-Pad Down  
        'Left': 1 << 12,# D-Pad Left
        'Right': 1 << 14,# D-Pad Right
        'l': 1 << 6,    # L
        'r': 1 << 7,    # R
        'o': 1 << 8,    # ZL
        'p': 1 << 9,    # ZR
    }

    KEYBOARD_STICK_MAP = {
        'w': ('ly', 1),   
        's': ('ly', -1),  
        'a': ('lx', -1),  
        'd': ('lx', 1),   
    }
    
    STICK_SENSITIVITY = 32767

    def __init__(self, root):
        self.root = root
        self.root.title("parsec 2 switch tool")
        self.root.geometry("780x670") 
        
        pygame.init()
        pygame.joystick.init()
        
        self.switch_conn = None
        self.controllers = {}
        self.num_players = 4 
        self.port_vars = {}
        self.active_joysticks = {}
        
        self.root.bind("<KeyPress>", self._on_keyboard_press)
        self.root.bind("<KeyRelease>", self._on_keyboard_release)
        self.pressed_keys = set()
        
        self._load_icon()
        self._build_ui()
        self._refresh_pc_joysticks()
        
        self.root.after(10, self._poll_hardware_events)

    def _load_icon(self):
        img_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "pro_controller.png")
        self.icon_image = None
        try:
            raw_img = tk.PhotoImage(file=img_path)
            if raw_img.width() > 100:
                self.icon_image = raw_img.subsample(raw_img.width() // 48, raw_img.height() // 48)
            else:
                self.icon_image = raw_img
        except Exception as e:
            print(f"Failed to process image: {e}")

    def set_connection(self, ip):
        self.switch_conn = SwitchConnection(ip)
        self.switch_conn.start(ip, active_count=self.num_players) 
        
        self.controllers = {i: VirtualController(self.switch_conn, i) for i in range(1, self.num_players + 1)}
        
        for controller in self.controllers.values():
            controller.activate()
            controller.blue_screen_clear()

    def _build_ui(self):
        self.ip_frame = ttk.LabelFrame(self.root, text="Connect Options", padding=10)
        self.ip_frame.pack(fill="x", padx=15, pady=10)
        
        ttk.Label(self.ip_frame, text="Switch IP:").pack(side="left", padx=2)
        self.ip_entry = ttk.Entry(self.ip_frame, width=14)
        self.ip_entry.insert(0, "192.168.1.48")
        self.ip_entry.pack(side="left", padx=5)
        
        ttk.Label(self.ip_frame, text="Players:").pack(side="left", padx=5)
        self.player_count_var = tk.StringVar(value="4")
        self.player_count_dropdown = ttk.Combobox(self.ip_frame, textvariable=self.player_count_var, values=[str(x) for x in range(1, 8)], width=4, state="readonly")
        self.player_count_dropdown.pack(side="left", padx=2)
        self.player_count_dropdown.bind("<<ComboboxSelected>>", self._on_player_count_changed)

        # unstable warning label for 5+ controllers
        self.warning_lbl = tk.Label(self.ip_frame, text="⚠️ 5+ Players can be unstable", fg="darkorange", font=("TkDefaultFont", 9, "bold"))
        self.warning_lbl.pack_forget()

        self.conn_btn = ttk.Button(self.ip_frame, text="Connect", command=self._toggle_connection)
        self.conn_btn.pack(side="left", padx=10)

        self.container_frame = ttk.Frame(self.root)
        self.container_frame.pack(fill="both", expand=True, padx=15, pady=5)

        self.canvas = tk.Canvas(self.container_frame, borderwidth=0, highlightthickness=0)
        self.scrollbar = ttk.Scrollbar(self.container_frame, orient="vertical", command=self.canvas.yview)
        self.routing_frame = ttk.LabelFrame(self.canvas, text="Assign Controllers (Connect to configure)", padding=10)
        
        self.routing_frame.bind(
            "<Configure>", 
            lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all"))
        )
        
        self.canvas_window = self.canvas.create_window((0, 0), window=self.routing_frame, anchor="nw")
        self.canvas.configure(yscrollcommand=self.scrollbar.set)
        
        self.canvas.pack(side="left", fill="both", expand=True)
        self.scrollbar.pack(side="right", fill="y")

        self.routing_frame.bind('<Configure>', lambda event: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.root.bind('<Configure>', lambda event: self.canvas.itemconfig(self.canvas_window, width=self.canvas.winfo_width()))

        footer = ttk.Frame(self.root, padding=5)
        footer.pack(fill="x", side="bottom")
        self.rescan_btn = ttk.Button(footer, text="Refresh Gamepads", command=self._refresh_pc_joysticks)
        self.rescan_btn.pack(side="right", padx=15)
        self.status_lbl = ttk.Label(footer, text="Disconnected", foreground="gray")
        self.status_lbl.pack(side="left", padx=15)

    def _on_player_count_changed(self, event):
        try:
            val = int(self.player_count_var.get())
            if val >= 5:
                self.warning_lbl.pack(side="left", padx=5)
            else:
                self.warning_lbl.pack_forget()
        except ValueError:
            pass

    def _render_controller_rows(self):
        for widget in self.routing_frame.winfo_children():
            widget.destroy()
            
        self.port_vars.clear()
        self.routing_frame.config(text=f"Assign controllers (Active: {self.num_players} Players)")

        for i in range(1, self.num_players + 1):
            row = ttk.Frame(self.routing_frame, padding=5)
            row.pack(fill="x", pady=2)
            
            if self.icon_image:
                img_lbl = ttk.Label(row, image=self.icon_image)
                img_lbl.pack(side="left", padx=(5, 15))
            
            ttk.Label(row, text=f"Controller {i}:", width=15).pack(side="left")
            ttk.Label(row, text="Assign controller:").pack(side="left", padx=10)
            
            gamepad_choice_var = tk.StringVar()
            dropdown = ttk.Combobox(row, textvariable=gamepad_choice_var, values=["None Connected"], width=25, state="readonly")
            dropdown.pack(side="left")
            dropdown.bind("<<ComboboxSelected>>", lambda event, idx=i: self._on_gamepad_source_change(idx))
            
            self.port_vars[i] = {
                "gamepad_source": gamepad_choice_var,
                "dropdown_widget": dropdown
            }

    def _refresh_pc_joysticks(self):
        pygame.joystick.quit()
        pygame.joystick.init()
        
        count = pygame.joystick.get_count()
        joystick_names = ["None Assigned", "Keyboard"]
        self.active_joysticks.clear()
        
        for i in range(count):
            try:
                j = pygame.joystick.Joystick(i)
                j.init()
                name_str = f"ID {i}: {j.get_name()[:15]}"
                joystick_names.append(name_str)
                self.active_joysticks[name_str] = j
            except:
                pass

        for i in self.port_vars.keys():
            self.port_vars[i]["dropdown_widget"].config(values=joystick_names)
            current_val = self.port_vars[i]["gamepad_source"].get()
            if current_val not in joystick_names:
                self.port_vars[i]["gamepad_source"].set(joystick_names[0])

    def _toggle_connection(self):
        if self.switch_conn is None:
            ip = self.ip_entry.get().strip()
            if not ip:
                messagebox.showerror("Error", "Please provide a valid Switch IP destination.")
                return
            
            try:
                self.num_players = int(self.player_count_var.get())
            except ValueError:
                self.num_players = 4

            self.ip_entry.config(state="disabled")
            self.player_count_dropdown.config(state="disabled")
            
            self._render_controller_rows()
            self._refresh_pc_joysticks()
            
            self.set_connection(ip)
            
            self.conn_btn.config(text="Disconnect")
            self.status_lbl.config(text=f"Cconnected to {ip} :)", foreground="green")
        else:
            if self.switch_conn:
                self.switch_conn.stop()
            self.switch_conn = None
            self.controllers.clear()
            
            for widget in self.routing_frame.winfo_children():
                widget.destroy()
            self.port_vars.clear()
            self.routing_frame.config(text="Waiting")

            self.conn_btn.config(text="Connect")
            self.ip_entry.config(state="normal")
            self.player_count_dropdown.config(state="readonly")
            self.status_lbl.config(text="Status: Disconnected", foreground="gray")

    def _on_gamepad_source_change(self, switch_port):
        if switch_port in self.controllers:
            self.controllers[switch_port].blue_screen_clear()

    def _on_keyboard_press(self, event):
        if not self.switch_conn: return
        
        key = event.keysym if event.keysym in ['Up', 'Down', 'Left', 'Right'] else event.char
        if key in self.KEYBOARD_MAP:
            bit = self.KEYBOARD_MAP[key]
            for p_num in range(1, self.num_players + 1):
                if p_num in self.port_vars and self.port_vars[p_num]["gamepad_source"].get() == "Keyboard":
                    self.controllers[p_num].set_button_by_bitmask(bit, True)
                    
        elif key in self.KEYBOARD_STICK_MAP:
            self.pressed_keys.add(key)
            self._update_keyboard_sticks()

    def _on_keyboard_release(self, event):
        if not self.switch_conn: return
        
        key = event.keysym if event.keysym in ['Up', 'Down', 'Left', 'Right'] else event.char
        if key in self.KEYBOARD_MAP:
            bit = self.KEYBOARD_MAP[key]
            for p_num in range(1, self.num_players + 1):
                if p_num in self.port_vars and self.port_vars[p_num]["gamepad_source"].get() == "Keyboard":
                    self.controllers[p_num].set_button_by_bitmask(bit, False)
                
        elif key in self.KEYBOARD_STICK_MAP:
            if key in self.pressed_keys:
                self.pressed_keys.remove(key)
            self._update_keyboard_sticks()
    
    def _update_keyboard_sticks(self):
        lx, ly = 0, 0
        for key in self.pressed_keys:
            if key in self.KEYBOARD_STICK_MAP:
                axis, multiplier = self.KEYBOARD_STICK_MAP[key]
                if axis == 'lx':
                    lx += multiplier * self.STICK_SENSITIVITY
                elif axis == 'ly':
                    ly += multiplier * self.STICK_SENSITIVITY

        lx = max(-32767, min(32767, lx))
        ly = max(-32767, min(32767, ly))

        for p_num in range(1, self.num_players + 1):
            if p_num in self.port_vars and self.port_vars[p_num]["gamepad_source"].get() == "Keyboard":
                v_con = self.controllers[p_num]
                v_con.lx = lx
                v_con.ly = ly
                v_con._push()

    def _poll_hardware_events(self):
        pygame.event.pump()
        
        if self.switch_conn is not None and self.switch_conn.is_running:
            for switch_port in range(1, self.num_players + 1):
                if switch_port not in self.port_vars: 
                    continue
                    
                selected_name = self.port_vars[switch_port]["gamepad_source"].get()
                if selected_name == "Keyboard":
                    continue

                if selected_name not in self.active_joysticks:
                    if switch_port in self.controllers:
                        self.controllers[switch_port].blue_screen_clear()
                    continue
                    
                joy = self.active_joysticks[selected_name]
                v_con = self.controllers[switch_port]
                
                current_mask = 0
                for pygame_idx, switch_bit in self.PYGAME_BUTTON_MAP.items():
                    if pygame_idx < joy.get_numbuttons() and joy.get_button(pygame_idx):
                        current_mask |= switch_bit
                        
                if joy.get_numaxes() >= 5:
                    if joy.get_axis(2) > 0.4: current_mask |= (1 << 8)   # ZL
                    if joy.get_axis(5) > 0.4: current_mask |= (1 << 9)   # ZR
                    
                if joy.get_numhats() > 0:
                    hat_x, hat_y = joy.get_hat(0)
                    if hat_y == 1:  current_mask |= (1 << 13) # DU
                    if hat_y == -1: current_mask |= (1 << 15) # DD
                    if hat_x == -1: current_mask |= (1 << 12) # DL
                    if hat_x == 1:  current_mask |= (1 << 14) # DR

                v_con.buttons_state = current_mask
                
                lx, ly, rx, ry = 0, 0, 0, 0
                if joy.get_numaxes() >= 4:
                    lx = int(joy.get_axis(0) * 32767)
                    ly = int(-joy.get_axis(1) * 32767)
                    rx = int(joy.get_axis(3) * 32767)
                    ry = int(-joy.get_axis(4) * 32767)
                    
                    if abs(lx) < 4500: lx = 0
                    if abs(ly) < 4500: ly = 0
                    if abs(rx) < 4500: rx = 0
                    if abs(ry) < 4500: ry = 0

                v_con.set_sticks(lx, ly, rx, ry)

        self.root.after(10, self._poll_hardware_events)


if __name__ == "__main__":
    root = tk.Tk()
    app = SmashParsecGUI(root)
    
    try:
        root.mainloop()
    finally:
        if app.switch_conn:
            app.switch_conn.stop()
        pygame.quit()