"""
MediBook Pro — Doctor Appointment Booking Chatbot
Powered by Google Gemini AI | Python + CustomTkinter + SQLite
"""

import os
import re
import json
import sqlite3
import threading
import datetime
import tkinter as tk
from tkinter import messagebox
import customtkinter as ctk

try:
    import google.generativeai as genai
    GEMINI_AVAILABLE = True
except ImportError:
    GEMINI_AVAILABLE = False
    print("Install google-generativeai: pip install google-generativeai")

# ─────────────────────────────────────────────
#  CONFIG  —  put your Gemini API key here
# ─────────────────────────────────────────────
GEMINI_API_KEY = "YOUR API KEY HERE"   # <── replace this
GEMINI_MODEL   = "gemini-2.5-flash"

DOCTORS = {
    "General Physician": ["Dr. Ahmed Khan", "Dr. Sara Malik"],
    "Cardiologist":      ["Dr. Imran Siddiqui"],
    "Dermatologist":     ["Dr. Nadia Hussain", "Dr. Bilal Awan"],
    "Pediatrician":      ["Dr. Ayesha Qureshi"],
    "Orthopedic":        ["Dr. Tariq Mehmood"],
    "ENT Specialist":    ["Dr. Zara Farooq"],
    "Gynecologist":      ["Dr. Fariha Noor"],
}

TIME_SLOTS = [
    "09:00 AM", "09:30 AM", "10:00 AM", "10:30 AM",
    "11:00 AM", "11:30 AM", "12:00 PM", "12:30 PM",
    "02:00 PM", "02:30 PM", "03:00 PM", "03:30 PM",
    "04:00 PM", "04:30 PM", "05:00 PM", "05:30 PM",
    "06:00 PM", "06:30 PM", "07:00 PM", "07:30 PM",
]

SYSTEM_PROMPT = """You are MediBook, a warm and professional doctor appointment booking assistant for a Pakistani clinic.

Your job is to collect these details ONE AT A TIME through natural conversation:
1. Patient full name
2. Doctor specialty (from: General Physician, Cardiologist, Dermatologist, Pediatrician, Orthopedic, ENT Specialist, Gynecologist)
3. Preferred date (must be today or a future date)
4. Preferred time slot (from the available slots shown to the user)
5. Patient contact number (Pakistani format preferred)

RULES:
- Ask ONE question at a time, keep responses short (2-3 lines max).
- When you have collected ALL 5 details, output EXACTLY this JSON block (nothing else after it):
  BOOKING_DATA:{"name":"...","specialty":"...","date":"YYYY-MM-DD","time":"HH:MM AM/PM","phone":"..."}
- If the user asks to cancel or reset, reply with: ACTION:RESET
- If the user asks to view appointments, reply with: ACTION:VIEW
- Be friendly, use simple English. Mention that slots may be unavailable if already booked.
- Today's date is """ + datetime.date.today().strftime("%A, %d %B %Y") + "."


# ─────────────────────────────────────────────
#  DATABASE
# ─────────────────────────────────────────────

class AppointmentDB:
    def __init__(self, db_path="medibook_appointments.db"):
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self._create_table()

    def _create_table(self):
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS appointments (
                id        INTEGER PRIMARY KEY AUTOINCREMENT,
                ref       TEXT UNIQUE,
                name      TEXT,
                specialty TEXT,
                doctor    TEXT,
                date      TEXT,
                time      TEXT,
                phone     TEXT,
                status    TEXT DEFAULT 'Confirmed',
                created   TEXT
            )
        """)
        self.conn.commit()

    def is_slot_taken(self, doctor, date, time):
        cur = self.conn.execute(
            "SELECT id FROM appointments WHERE doctor=? AND date=? AND time=? AND status='Confirmed'",
            (doctor, date, time)
        )
        return cur.fetchone() is not None

    def book(self, name, specialty, date, time, phone):
        """Returns (success, ref_or_error, doctor)"""
        # pick first available doctor for specialty
        doctors = DOCTORS.get(specialty, [])
        chosen_doctor = None
        for doc in doctors:
            if not self.is_slot_taken(doc, date, time):
                chosen_doctor = doc
                break

        if not chosen_doctor:
            return False, f"Sorry, all doctors for {specialty} are fully booked at {time} on {date}.", None

        import random, string
        ref = "APT-" + "".join(random.choices(string.digits, k=6))
        now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        self.conn.execute(
            "INSERT INTO appointments (ref,name,specialty,doctor,date,time,phone,status,created) "
            "VALUES (?,?,?,?,?,?,?,?,?)",
            (ref, name, specialty, chosen_doctor, date, time, phone, "Confirmed", now)
        )
        self.conn.commit()
        return True, ref, chosen_doctor

    def get_all(self):
        cur = self.conn.execute(
            "SELECT ref,name,specialty,doctor,date,time,phone,status FROM appointments ORDER BY date,time"
        )
        return cur.fetchall()

    def cancel(self, ref):
        cur = self.conn.execute(
            "UPDATE appointments SET status='Cancelled' WHERE ref=? AND status='Confirmed'", (ref,)
        )
        self.conn.commit()
        return cur.rowcount > 0

    def get_booked_slots(self, date_str):
        cur = self.conn.execute(
            "SELECT doctor, time FROM appointments WHERE date=? AND status='Confirmed'", (date_str,)
        )
        return cur.fetchall()


# ─────────────────────────────────────────────
#  GEMINI CLIENT
# ─────────────────────────────────────────────

class GeminiClient:
    def __init__(self, api_key):
        if not GEMINI_AVAILABLE:
            raise RuntimeError("google-generativeai not installed.")
        genai.configure(api_key=api_key)
        self.model = genai.GenerativeModel(
            model_name=GEMINI_MODEL,
            system_instruction=SYSTEM_PROMPT
        )
        self.chat = self.model.start_chat(history=[])

    def send(self, message):
        response = self.chat.send_message(message)
        return response.text

    def reset(self):
        self.chat = self.model.start_chat(history=[])


# ─────────────────────────────────────────────
#  MAIN APPLICATION
# ─────────────────────────────────────────────

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("green")


class MediBookApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("MediBook Pro — Doctor Appointment Booking")
        self.geometry("1080x700")
        self.minsize(900, 600)
        self.configure(fg_color="#0d1117")

        self.db = AppointmentDB()
        self.gemini: GeminiClient | None = None

        self._build_ui()
        self._check_api_key()

    # ── UI BUILD ───────────────────────────────

    def _build_ui(self):
        self.grid_columnconfigure(0, weight=3)
        self.grid_columnconfigure(1, weight=2)
        self.grid_rowconfigure(0, weight=1)

        self._build_chat_panel()
        self._build_right_panel()

    def _build_chat_panel(self):
        left = ctk.CTkFrame(self, fg_color="#161b22", corner_radius=0)
        left.grid(row=0, column=0, sticky="nsew")
        left.grid_rowconfigure(1, weight=1)
        left.grid_columnconfigure(0, weight=1)

        # Header
        hdr = ctk.CTkFrame(left, fg_color="#1a7a5a", corner_radius=0, height=60)
        hdr.grid(row=0, column=0, sticky="ew")
        hdr.grid_propagate(False)

        ctk.CTkLabel(
            hdr, text="🏥  MediBook Assistant",
            font=ctk.CTkFont(family="Segoe UI", size=17, weight="bold"),
            text_color="#ffffff"
        ).pack(side="left", padx=20, pady=15)

        self.status_dot = ctk.CTkLabel(hdr, text="● Online", text_color="#5DCAA5",
                                        font=ctk.CTkFont(size=12))
        self.status_dot.pack(side="right", padx=20)

        # Chat area
        self.chat_frame = ctk.CTkScrollableFrame(
            left, fg_color="#0d1117", corner_radius=0,
            scrollbar_button_color="#1a7a5a"
        )
        self.chat_frame.grid(row=1, column=0, sticky="nsew", padx=0, pady=0)
        self.chat_frame.grid_columnconfigure(0, weight=1)

        # Input area
        inp_frame = ctk.CTkFrame(left, fg_color="#161b22", corner_radius=0, height=70)
        inp_frame.grid(row=2, column=0, sticky="ew")
        inp_frame.grid_propagate(False)
        inp_frame.grid_columnconfigure(0, weight=1)

        self.msg_input = ctk.CTkEntry(
            inp_frame,
            placeholder_text="Type your message…",
            font=ctk.CTkFont(size=14),
            fg_color="#21262d",
            border_color="#30363d",
            border_width=1,
            text_color="#e6edf3",
            corner_radius=10,
            height=42
        )
        self.msg_input.grid(row=0, column=0, padx=(16, 8), pady=14, sticky="ew")
        self.msg_input.bind("<Return>", lambda e: self._on_send())

        self.send_btn = ctk.CTkButton(
            inp_frame, text="Send ➤", width=90, height=42,
            fg_color="#1a7a5a", hover_color="#0F6E56",
            font=ctk.CTkFont(size=13, weight="bold"),
            corner_radius=10,
            command=self._on_send
        )
        self.send_btn.grid(row=0, column=1, padx=(0, 16), pady=14)

        self.reset_btn = ctk.CTkButton(
            inp_frame, text="↺ Reset", width=80, height=42,
            fg_color="#21262d", hover_color="#30363d",
            border_color="#30363d", border_width=1,
            font=ctk.CTkFont(size=13),
            corner_radius=10,
            command=self._reset_chat
        )
        self.reset_btn.grid(row=0, column=2, padx=(0, 16), pady=14)

    def _build_right_panel(self):
        right = ctk.CTkFrame(self, fg_color="#161b22", corner_radius=0)
        right.grid(row=0, column=1, sticky="nsew")
        right.grid_rowconfigure(2, weight=1)
        right.grid_columnconfigure(0, weight=1)

        # API Key section
        api_frame = ctk.CTkFrame(right, fg_color="#21262d", corner_radius=10)
        api_frame.grid(row=0, column=0, sticky="ew", padx=14, pady=(14, 6))
        api_frame.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(api_frame, text="Gemini API Key",
                     font=ctk.CTkFont(size=12, weight="bold"),
                     text_color="#8b949e").grid(row=0, column=0, sticky="w", padx=12, pady=(10, 2))

        key_row = ctk.CTkFrame(api_frame, fg_color="transparent")
        key_row.grid(row=1, column=0, sticky="ew", padx=10, pady=(0, 10))
        key_row.grid_columnconfigure(0, weight=1)

        self.api_entry = ctk.CTkEntry(
            key_row, show="•", height=36,
            placeholder_text="Paste your API key…",
            fg_color="#0d1117", border_color="#30363d",
            text_color="#e6edf3", corner_radius=8
        )
        self.api_entry.grid(row=0, column=0, sticky="ew", padx=(0, 6))
        if GEMINI_API_KEY != "YOUR_GEMINI_API_KEY_HERE":
            self.api_entry.insert(0, GEMINI_API_KEY)

        ctk.CTkButton(
            key_row, text="✓", width=36, height=36,
            fg_color="#1a7a5a", hover_color="#0F6E56",
            corner_radius=8, command=self._init_gemini
        ).grid(row=0, column=1)

        # Available slots panel
        slots_frame = ctk.CTkFrame(right, fg_color="#21262d", corner_radius=10)
        slots_frame.grid(row=1, column=0, sticky="ew", padx=14, pady=6)
        slots_frame.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(slots_frame, text="Check Available Slots",
                     font=ctk.CTkFont(size=12, weight="bold"),
                     text_color="#8b949e").grid(row=0, column=0, sticky="w", padx=12, pady=(10, 4))

        slot_row = ctk.CTkFrame(slots_frame, fg_color="transparent")
        slot_row.grid(row=1, column=0, sticky="ew", padx=10, pady=(0, 10))
        slot_row.grid_columnconfigure(0, weight=1)

        self.date_entry = ctk.CTkEntry(
            slot_row, height=32, placeholder_text="YYYY-MM-DD",
            fg_color="#0d1117", border_color="#30363d",
            text_color="#e6edf3", corner_radius=8
        )
        self.date_entry.grid(row=0, column=0, sticky="ew", padx=(0, 6))
        self.date_entry.insert(0, datetime.date.today().strftime("%Y-%m-%d"))

        ctk.CTkButton(
            slot_row, text="Check", width=60, height=32,
            fg_color="#21262d", hover_color="#30363d",
            border_color="#30363d", border_width=1,
            corner_radius=8, command=self._check_slots
        ).grid(row=0, column=1)

        self.slots_label = ctk.CTkLabel(
            slots_frame, text="", font=ctk.CTkFont(size=11),
            text_color="#8b949e", wraplength=260, justify="left"
        )
        self.slots_label.grid(row=2, column=0, sticky="w", padx=12, pady=(0, 8))

        # Appointments list
        appt_hdr = ctk.CTkFrame(right, fg_color="transparent")
        appt_hdr.grid(row=2, column=0, sticky="nsew", padx=14, pady=6)
        appt_hdr.grid_rowconfigure(1, weight=1)
        appt_hdr.grid_columnconfigure(0, weight=1)

        hdr_row = ctk.CTkFrame(appt_hdr, fg_color="transparent")
        hdr_row.grid(row=0, column=0, sticky="ew")

        ctk.CTkLabel(hdr_row, text="All Appointments",
                     font=ctk.CTkFont(size=13, weight="bold"),
                     text_color="#e6edf3").pack(side="left")

        ctk.CTkButton(
            hdr_row, text="↻ Refresh", width=80, height=28,
            fg_color="#21262d", hover_color="#30363d",
            border_color="#30363d", border_width=1,
            font=ctk.CTkFont(size=11), corner_radius=6,
            command=self._load_appointments
        ).pack(side="right")

        self.appt_scroll = ctk.CTkScrollableFrame(
            appt_hdr, fg_color="#0d1117", corner_radius=8,
            scrollbar_button_color="#1a7a5a"
        )
        self.appt_scroll.grid(row=1, column=0, sticky="nsew", pady=(8, 0))
        self.appt_scroll.grid_columnconfigure(0, weight=1)

        # Cancel section
        cancel_frame = ctk.CTkFrame(right, fg_color="#21262d", corner_radius=10)
        cancel_frame.grid(row=3, column=0, sticky="ew", padx=14, pady=(6, 14))
        cancel_frame.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(cancel_frame, text="Cancel Appointment",
                     font=ctk.CTkFont(size=12, weight="bold"),
                     text_color="#8b949e").grid(row=0, column=0, sticky="w", padx=12, pady=(10, 4))

        c_row = ctk.CTkFrame(cancel_frame, fg_color="transparent")
        c_row.grid(row=1, column=0, sticky="ew", padx=10, pady=(0, 10))
        c_row.grid_columnconfigure(0, weight=1)

        self.cancel_entry = ctk.CTkEntry(
            c_row, height=32, placeholder_text="APT-XXXXXX",
            fg_color="#0d1117", border_color="#30363d",
            text_color="#e6edf3", corner_radius=8
        )
        self.cancel_entry.grid(row=0, column=0, sticky="ew", padx=(0, 6))

        ctk.CTkButton(
            c_row, text="Cancel", width=70, height=32,
            fg_color="#8b1a1a", hover_color="#6b1414",
            corner_radius=8, command=self._cancel_appointment
        ).grid(row=0, column=1)

    # ── LOGIC ──────────────────────────────────

    def _check_api_key(self):
        if GEMINI_API_KEY != "YOUR_GEMINI_API_KEY_HERE":
            self._init_gemini(auto=True)
        else:
            self._add_bot_bubble(
                "👋 Welcome to MediBook Pro!\n\n"
                "Please paste your Gemini API key in the panel on the right, "
                "then click ✓ to connect."
            )
        self._load_appointments()

    def _init_gemini(self, auto=False):
        key = self.api_entry.get().strip()
        if not key:
            messagebox.showwarning("API Key", "Please enter your Gemini API key.")
            return
        try:
            self.status_dot.configure(text="● Connecting…", text_color="#f0a500")
            self.update()
            self.gemini = GeminiClient(key)
            self.status_dot.configure(text="● Online", text_color="#5DCAA5")
            if not auto:
                self._add_bot_bubble("✅ Gemini connected! Starting fresh session…")
                self._reset_chat(init=True)
            else:
                self._start_conversation()
        except Exception as e:
            self.status_dot.configure(text="● Error", text_color="#e24b4a")
            messagebox.showerror("Connection Error", str(e))

    def _start_conversation(self):
        if not self.gemini:
            return
        self._add_bot_bubble("Connecting to Gemini AI…")
        threading.Thread(target=self._gemini_init_thread, daemon=True).start()

    def _gemini_init_thread(self):
        try:
            reply = self.gemini.send("Hello, I need to book a doctor appointment.")
            self.after(0, self._handle_reply, reply)
        except Exception as e:
            self.after(0, self._add_bot_bubble, f"Error: {e}")

    def _on_send(self):
        if not self.gemini:
            messagebox.showinfo("Not Connected", "Please add your Gemini API key first.")
            return
        text = self.msg_input.get().strip()
        if not text:
            return
        self.msg_input.delete(0, "end")
        self._add_user_bubble(text)
        self.send_btn.configure(state="disabled", text="…")
        threading.Thread(target=self._send_thread, args=(text,), daemon=True).start()

    def _send_thread(self, text):
        try:
            reply = self.gemini.send(text)
            self.after(0, self._handle_reply, reply)
        except Exception as e:
            self.after(0, self._add_bot_bubble, f"⚠ Error: {e}")
        finally:
            self.after(0, lambda: self.send_btn.configure(state="normal", text="Send ➤"))

    def _handle_reply(self, reply: str):
        # Check for booking data
        if "BOOKING_DATA:" in reply:
            # Extract text before JSON and show it
            parts = reply.split("BOOKING_DATA:")
            if parts[0].strip():
                self._add_bot_bubble(parts[0].strip())
            json_str = parts[1].strip()
            try:
                data = json.loads(json_str)
                self._process_booking(data)
            except json.JSONDecodeError:
                self._add_bot_bubble("⚠ Could not parse booking data. Please try again.")
            return

        if "ACTION:RESET" in reply:
            self._reset_chat()
            return

        if "ACTION:VIEW" in reply:
            self._add_bot_bubble("Here are the current appointments — check the panel on the right! ➡")
            self._load_appointments()
            return

        self._add_bot_bubble(reply)

    def _process_booking(self, data):
        name     = data.get("name", "")
        specialty = data.get("specialty", "")
        date     = data.get("date", "")
        time     = data.get("time", "")
        phone    = data.get("phone", "")

        # Validate date
        try:
            appt_date = datetime.date.fromisoformat(date)
            if appt_date < datetime.date.today():
                self._add_bot_bubble("❌ The date you selected is in the past. Please choose a future date.")
                return
        except ValueError:
            self._add_bot_bubble(f"❌ Invalid date format: {date}. Please provide YYYY-MM-DD.")
            return

        # Validate specialty
        if specialty not in DOCTORS:
            self._add_bot_bubble(
                f"❌ '{specialty}' is not a recognised specialty.\n"
                f"Available: {', '.join(DOCTORS.keys())}"
            )
            return

        # Try booking
        success, result, doctor = self.db.book(name, specialty, date, time, phone)

        if success:
            msg = (
                f"✅ Appointment Confirmed!\n\n"
                f"📋 Ref: {result}\n"
                f"👤 Patient: {name}\n"
                f"🏥 Doctor: {doctor}\n"
                f"🩺 Specialty: {specialty}\n"
                f"📅 Date: {appt_date.strftime('%A, %d %B %Y')}\n"
                f"🕐 Time: {time}\n"
                f"📞 Contact: {phone}\n\n"
                f"Please keep your reference number for cancellations."
            )
            self._add_bot_bubble(msg, color="#1a3a2a")
            self._load_appointments()
            # Reset for next booking
            self.after(500, lambda: self.gemini.reset() if self.gemini else None)
        else:
            self._add_bot_bubble(f"⚠ Booking failed:\n{result}\n\nWould you like to choose a different time?")

    def _reset_chat(self, init=False):
        # Clear chat
        for w in self.chat_frame.winfo_children():
            w.destroy()
        if self.gemini:
            self.gemini.reset()
        if not init:
            self._start_conversation()

    def _check_slots(self):
        date_str = self.date_entry.get().strip()
        try:
            datetime.date.fromisoformat(date_str)
        except ValueError:
            self.slots_label.configure(text="❌ Invalid date. Use YYYY-MM-DD")
            return

        booked = self.db.get_booked_slots(date_str)
        booked_set = set((doc, t) for doc, t in booked)

        lines = []
        for slot in TIME_SLOTS[:8]:  # show first 8
            taken_docs = [doc for doc, t in booked_set if t == slot]
            if taken_docs:
                lines.append(f"🔴 {slot} — {', '.join(taken_docs)} booked")
            else:
                lines.append(f"🟢 {slot} — available")

        self.slots_label.configure(text="\n".join(lines))

    def _load_appointments(self):
        for w in self.appt_scroll.winfo_children():
            w.destroy()

        rows = self.db.get_all()
        if not rows:
            ctk.CTkLabel(
                self.appt_scroll, text="No appointments yet.",
                text_color="#8b949e", font=ctk.CTkFont(size=12)
            ).pack(pady=20)
            return

        for ref, name, spec, doctor, date, time, phone, status in rows:
            card = ctk.CTkFrame(
                self.appt_scroll,
                fg_color="#1a7a5a22" if status == "Confirmed" else "#8b1a1a22",
                corner_radius=8,
                border_width=1,
                border_color="#1a7a5a55" if status == "Confirmed" else "#8b1a1a55"
            )
            card.pack(fill="x", pady=3, padx=2)

            badge_color = "#1a7a5a" if status == "Confirmed" else "#8b1a1a"
            top = ctk.CTkFrame(card, fg_color="transparent")
            top.pack(fill="x", padx=10, pady=(8, 0))

            ctk.CTkLabel(
                top, text=ref,
                font=ctk.CTkFont(size=11, weight="bold"),
                text_color="#5DCAA5" if status == "Confirmed" else "#e24b4a"
            ).pack(side="left")

            ctk.CTkLabel(
                top, text=status,
                font=ctk.CTkFont(size=10),
                text_color="#5DCAA5" if status == "Confirmed" else "#e24b4a"
            ).pack(side="right")

            ctk.CTkLabel(
                card,
                text=f"{name}  •  {spec}\n{doctor}\n{date}  {time}  •  {phone}",
                font=ctk.CTkFont(size=11),
                text_color="#c9d1d9",
                justify="left",
                anchor="w"
            ).pack(fill="x", padx=10, pady=(2, 8))

    def _cancel_appointment(self):
        ref = self.cancel_entry.get().strip()
        if not ref:
            messagebox.showwarning("Cancel", "Enter an appointment reference (APT-XXXXXX).")
            return
        if messagebox.askyesno("Confirm Cancellation", f"Cancel appointment {ref}?"):
            if self.db.cancel(ref):
                messagebox.showinfo("Cancelled", f"{ref} has been cancelled.")
                self.cancel_entry.delete(0, "end")
                self._load_appointments()
            else:
                messagebox.showerror("Not Found", f"No active appointment found for {ref}.")

    # ── BUBBLE HELPERS ─────────────────────────

    def _add_bot_bubble(self, text, color="#21262d"):
        row = ctk.CTkFrame(self.chat_frame, fg_color="transparent")
        row.pack(fill="x", padx=12, pady=4, anchor="w")

        icon = ctk.CTkLabel(row, text="🏥", font=ctk.CTkFont(size=16), width=30)
        icon.pack(side="left", anchor="n", pady=4)

        bubble = ctk.CTkLabel(
            row, text=text,
            fg_color=color,
            corner_radius=12,
            wraplength=380,
            justify="left",
            anchor="w",
            font=ctk.CTkFont(size=13),
            text_color="#e6edf3",
            padx=14, pady=10
        )
        bubble.pack(side="left", fill="x", padx=(4, 60))
        self._scroll_bottom()

    def _add_user_bubble(self, text):
        row = ctk.CTkFrame(self.chat_frame, fg_color="transparent")
        row.pack(fill="x", padx=12, pady=4, anchor="e")

        bubble = ctk.CTkLabel(
            row, text=text,
            fg_color="#1a7a5a",
            corner_radius=12,
            wraplength=360,
            justify="right",
            anchor="e",
            font=ctk.CTkFont(size=13),
            text_color="#ffffff",
            padx=14, pady=10
        )
        bubble.pack(side="right", padx=(60, 4))
        ctk.CTkLabel(row, text="👤", font=ctk.CTkFont(size=16), width=30).pack(
            side="right", anchor="n", pady=4
        )
        self._scroll_bottom()

    def _scroll_bottom(self):
        self.update_idletasks()
        self.chat_frame._parent_canvas.yview_moveto(1.0)


# ─────────────────────────────────────────────
#  ENTRY POINT
# ─────────────────────────────────────────────

if __name__ == "__main__":
    if not GEMINI_AVAILABLE:
        import sys
        print("\n❌  Missing dependency. Run:\n")
        print("    pip install google-generativeai customtkinter\n")
        sys.exit(1)

    app = MediBookApp()
    app.mainloop()