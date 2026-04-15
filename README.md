# 🏥 MediBook Pro — AI-Powered Doctor Appointment Booking

MediBook Pro is a modern, conversational desktop application designed to streamline doctor appointment bookings. Built with Python and a sleek CustomTkinter interface, the application integrates **Google Gemini AI** to act as a smart receptionist. It guides patients through a natural chat interface to collect booking details, checks availability, and manages appointments via a local SQLite database. 

Designed specifically with Pakistani clinics in mind, it handles various medical specialties and provides a frictionless user experience.

## ✨ Features

* **Conversational AI Assistant:** Powered by `gemini-2.5-flash`, the chatbot collects patient details (name, specialty, date, time, phone) through natural, step-by-step dialogue.
* **Modern Dark-Mode UI:** Built with `customtkinter` for a polished, responsive, and visually appealing desktop experience.
* **Real-Time Slot Checking:** Automatically queries the database to prevent double-booking for specific doctors and time slots.
* **Database Management:** Uses SQLite (`appointments.db`) to securely store, retrieve, and cancel appointments.
* **In-App Controls:** Features a dedicated side-panel to instantly view all active appointments, check daily slot availability, and process cancellations.
* **Dynamic API Key Input:** Users can securely paste their Gemini API key directly into the application's UI to start the chatbot.

## 🛠️ Tech Stack

* **Language:** Python 3.x
* **AI Integration:** Google Generative AI API (`google-generativeai`)
* **GUI Framework:** CustomTkinter (`customtkinter`)
* **Database:** SQLite3 (Built-in)

## 🚀 Installation & Setup

**1. Clone the repository**
```bash
git clone [https://github.com/YourUsername/MediBook-Pro.git](https://github.com/YourUsername/MediBook-Pro.git)
cd MediBook-Pro# Doctorslotbooking
MediBook Pro — AI-Powered Doctor Appointment Booking
