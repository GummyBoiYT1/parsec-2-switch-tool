import socket
import struct
import threading
import time
import tkinter as tk
from tkinter import messagebox, ttk
import pygame

class ParsecToSwitchClient:
    CLIENT_PACKET_FORMAT = "<32sIiiii" 

    def __init__(self, root):
        self.root = root
        self.root.title("parsec 2 switch tool - client")
        self.root.geometry("420x360")
        
        pygame.init()
        pygame.joystick.init()
        
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.is_running = False
        self.network_thread = None
        
        self.pressed_keys = set()
        self.buttons_state = 0
        self.lx, self.ly, self.rx, self.ry = 0, 0, 0, 0
        
        self.PYGAME_BUTTON_MAP = {0: 1, 1: 1<<1, 2: 1<<2, 3: 1<<3, 4: 1<<11, 6: 1<<10, 7: 1<<4, 8: 1<<5, 9: 1<<6, 10: 1<<7}
        self.KEYBOARD_MAP = {'j': 1, 'k': 1<<1, 'u': 1<<2, 'i': 1<<3, 'q': 1<<11, 'e': 1<<10, 'Up': 1<<13, 'Down': 1<<15, 'Left': 1<<12, 'Right': 1<<14, 'l': 1<<6, 'r': 1<<7, 'o': 1<<8, 'p': 1<<9}
        self.KEYBOARD_STICK_MAP = {'w': ('ly', 1), 's': ('ly', -1), 'a': ('lx', -1), 'd': ('lx', 1)}

        self._build_ui()
        self.root.bind("<KeyPress>", self._on_key_press)
        self.root.bind("<KeyRelease>", self._on_key_release)
        self.root.after(10, self._poll_input)

    def _build_ui(self):
        frame = ttk.LabelFrame(self.root, text="Options", padding=10)
        frame.pack(fill="both", expand=True, padx=15, pady=15)

        ttk.Label(frame, text="Username (Leave blank for Device Name):").pack(anchor="w", pady=2)
        self.user_entry = ttk.Entry(frame)
        self.user_entry.pack(fill="x", pady=5)

        ip_row = ttk.Frame(frame)
        ip_row.pack(fill="x", pady=5)

        ip_col = ttk.Frame(ip_row)
        ip_col.pack(side="left", fill="x", expand=True)
        ttk.Label(ip_col, text="Host IP:").pack(anchor="w", pady=2)
        self.ip_entry = ttk.Entry(ip_col)
        self.ip_entry.insert(0, "127.0.0.1")
        self.ip_entry.pack(fill="x")

        port_col = ttk.Frame(ip_row)
        port_col.pack(side="left", padx=(10, 0))
        ttk.Label(port_col, text="Port:").pack(anchor="w", pady=2)
        self.port_entry = ttk.Entry(port_col, width=8)
        self.port_entry.insert(0, "9000")
        self.port_entry.pack(side="left")

        ttk.Label(frame, text="Device to capture").pack(anchor="w", pady=2)
        self.source_var = tk.StringVar(value="Keyboard")
        self.source_dropdown = ttk.Combobox(frame, textvariable=self.source_var, state="readonly")
        self.source_dropdown.pack(fill="x", pady=5)

        btn_row = ttk.Frame(frame)
        btn_row.pack(fill="x", pady=10)

        self.conn_btn = ttk.Button(btn_row, text="Connect to Host", command=self._toggle_connection)
        self.conn_btn.pack(side="left", fill="x", expand=True, padx=(0, 5))

        self.kbd_btn = ttk.Button(btn_row, text="Configure Keyboard", command=self._open_keyboard_config)
        self.kbd_btn.pack(side="right", padx=(5, 0))
        
        self.status_lbl = ttk.Label(frame, text="Status: Disconnected", foreground="gray")
        self.status_lbl.pack(anchor="s", pady=5)
        
        count = pygame.joystick.get_count()
        choices = ["Keyboard"]
        for i in range(count):
            try:
                j = pygame.joystick.Joystick(i)
                j.init()
                choices.append(f"Gamepad ID {i}: {j.get_name()[:15]}")
            except: pass
        self.source_dropdown.config(values=choices)

    def _open_keyboard_config(self):
        config_win = tk.Toplevel(self.root)
        config_win.title("Keyboard Layout Configuration")
        config_win.geometry("400x550")
        config_win.grab_set()

        canvas = tk.Canvas(config_win, borderwidth=0, highlightthickness=0)
        scrollbar = ttk.Scrollbar(config_win, orient="vertical", command=canvas.yview)
        scroll_frame = ttk.Frame(canvas, padding=10)
        
        scroll_frame.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=scroll_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        ttk.Label(scroll_frame, text="Click a field and press a key to rebind it.", font=("TkDefaultFont", 10, "italic")).pack(pady=5)

        labels_map = {
            1: "Button A", 1<<1: "Button B", 1<<2: "Button X", 1<<3: "Button Y",
            1<<11: "Minus", 1<<10: "Plus", 1<<13: "D-Pad Up", 1<<15: "D-Pad Down",
            1<<12: "D-Pad Left", 1<<14: "D-Pad Right", 1<<6: "Button L", 1<<7: "Button R",
            1<<8: "Button ZL", 1<<9: "Button ZR"
        }
        stick_labels = {
            'ly_1': ("Left Stick Up", 'ly', 1), 'ly_-1': ("Left Stick Down", 'ly', -1),
            'lx_-1': ("Left Stick Left", 'lx', -1), 'lx_1': ("Left Stick Right", 'lx', 1)
        }

        entries = {}

        def start_listening(target_key, is_stick=False):
            entries[target_key].config(text="Press any key...")
            entries[target_key].focus_set()
            
            def capture_key(event):
                new_key = event.keysym if event.keysym in ['Up', 'Down', 'Left', 'Right'] else event.char
                if not new_key: return "break"
                
                if is_stick:
                    for k, v in list(self.KEYBOARD_STICK_MAP.items()):
                        if v == stick_labels[target_key][1:]:
                            del self.KEYBOARD_STICK_MAP[k]
                    self.KEYBOARD_STICK_MAP[new_key] = stick_labels[target_key][1:]
                else:
                    for k, v in list(self.KEYBOARD_MAP.items()):
                        if v == target_key:
                            del self.KEYBOARD_MAP[k]
                    self.KEYBOARD_MAP[new_key] = target_key
                
                entries[target_key].config(text=new_key)
                entries[target_key].unbind("<Key>")
                return "break"
                
            entries[target_key].bind("<Key>", capture_key)

        for bitmask, label_text in labels_map.items():
            row = ttk.Frame(scroll_frame, padding=2)
            row.pack(fill="x")
            ttk.Label(row, text=label_text, width=20).pack(side="left")
            current_key = next((k for k, v in self.KEYBOARD_MAP.items() if v == bitmask), "[None]")
            btn = ttk.Button(row, text=current_key, width=15)
            btn.pack(side="right")
            entries[bitmask] = btn
            btn.config(command=lambda b=bitmask: start_listening(b, False))

        ttk.Separator(scroll_frame, orient="horizontal").pack(fill="x", pady=10)

        for s_id, data in stick_labels.items():
            row = ttk.Frame(scroll_frame, padding=2)
            row.pack(fill="x")
            ttk.Label(row, text=data[0], width=20).pack(side="left")
            current_key = next((k for k, v in self.KEYBOARD_STICK_MAP.items() if v == data[1:]), "[None]")
            btn = ttk.Button(row, text=current_key, width=15)
            btn.pack(side="right")
            entries[s_id] = btn
            btn.config(command=lambda sid=s_id: start_listening(sid, True))

    def _toggle_connection(self):
        if not self.is_running:
            host_ip = self.ip_entry.get().strip()
            if not host_ip:
                messagebox.showerror("Error", "Please specify the Host IP.")
                return
            
            try:
                dest_port = int(self.port_entry.get().strip())
            except ValueError:
                messagebox.showerror("Error", "Please provide a valid numeric Port number.")
                return
     
            username = self.user_entry.get().strip()
            if not username:
                username = socket.gethostname()
           
            self.final_username = username[:30] 
            self.host_address = (host_ip, dest_port)
            self.is_running = True
            
            self.user_entry.config(state="disabled")
            self.ip_entry.config(state="disabled")
            self.port_entry.config(state="disabled")
            self.source_dropdown.config(state="disabled")
            self.conn_btn.config(text="Disconnect")
            self.status_lbl.config(text=f"streaming to {self.ip_entry.get()} as '{self.final_username}'", foreground="green")
            
            self.network_thread = threading.Thread(target=self._network_loop, daemon=True)
            self.network_thread.start()
        else:
            self.is_running = False
            if self.network_thread:
                self.network_thread.join()
            self.user_entry.config(state="normal")
            self.ip_entry.config(state="normal")
            self.port_entry.config(state="normal")
            self.source_dropdown.config(state="readonly")
            self.conn_btn.config(text="Connect")
            self.status_lbl.config(text="Disconnected", foreground="gray")

    def _on_key_press(self, event):
        if self.source_var.get() != "Keyboard": return
        key = event.keysym if event.keysym in ['Up', 'Down', 'Left', 'Right'] else event.char
        if key in self.KEYBOARD_MAP:
            self.buttons_state |= self.KEYBOARD_MAP[key]
        elif key in self.KEYBOARD_STICK_MAP:
            self.pressed_keys.add(key)
            self._update_keyboard_sticks()

    def _on_key_release(self, event):
        if self.source_var.get() != "Keyboard": return
        key = event.keysym if event.keysym in ['Up', 'Down', 'Left', 'Right'] else event.char
        if key in self.KEYBOARD_MAP:
            self.buttons_state &= ~self.KEYBOARD_MAP[key]
        elif key in self.KEYBOARD_STICK_MAP:
            if key in self.pressed_keys:
                self.pressed_keys.remove(key)
            self._update_keyboard_sticks()

    def _update_keyboard_sticks(self):
        self.lx, self.ly = 0, 0
        for key in self.pressed_keys:
            if key in self.KEYBOARD_STICK_MAP:
                axis, mult = self.KEYBOARD_STICK_MAP[key]
                if axis == 'lx': self.lx += mult * 32767
                elif axis == 'ly': self.ly += mult * 32767
        self.lx = max(-32767, min(32767, self.lx))
        self.ly = max(-32767, min(32767, self.ly))

    def _poll_input(self):
        pygame.event.pump()
        selected = self.source_var.get()
        
        if "Gamepad ID" in selected and self.is_running:
            try:
                joy_id = int(selected.split("ID ")[1].split(":")[0])
                joy = pygame.joystick.Joystick(joy_id)
                
                mask = 0
                for p_idx, bit in self.PYGAME_BUTTON_MAP.items():
                    if p_idx < joy.get_numbuttons() and joy.get_button(p_idx):
                        mask |= bit
                if joy.get_numaxes() >= 5:
                    if joy.get_axis(2) > 0.4: mask |= (1 << 8)
                    if joy.get_axis(5) > 0.4: mask |= (1 << 9)
                if joy.get_numhats() > 0:
                    hx, hy = joy.get_hat(0)
                    if hy == 1:  mask |= (1 << 13)
                    if hy == -1: mask |= (1 << 15)
                    if hx == -1: mask |= (1 << 12)
                    if hx == 1:  mask |= (1 << 14)
                
                self.buttons_state = mask
                
                if joy.get_numaxes() >= 4:
                    self.lx = int(joy.get_axis(0) * 32767)
                    self.ly = int(-joy.get_axis(1) * 32767)
                    self.rx = int(joy.get_axis(3) * 32767)
                    self.ry = int(-joy.get_axis(4) * 32767)
                    if abs(self.lx) < 4500: self.lx = 0
                    if abs(self.ly) < 4500: self.ly = 0
                    if abs(self.rx) < 4500: self.rx = 0
                    if abs(self.ry) < 4500: self.ry = 0
            except Exception: pass

        self.root.after(10, self._poll_input)

    def _network_loop(self):
        while self.is_running:
            try:
                # pack everything into one!
                encoded_name = self.final_username.encode('utf-8')
                packet = struct.pack(self.CLIENT_PACKET_FORMAT, encoded_name, self.buttons_state, self.lx, self.ly, self.rx, self.ry)
                self.sock.sendto(packet, self.host_address)
            except: pass
            time.sleep(1 / 60.0)

if __name__ == "__main__":
    root = tk.Tk()
    app = ParsecToSwitchClient(root)
    try: root.mainloop()
    finally: pygame.quit()
