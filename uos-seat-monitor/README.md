# 🎓 UoS Course Seat Monitor (University of Sharjah)

> **Get notified the exact second a seat opens in your required UoS classes!**  
> 🔔 **Phone Alerts (iPhone & Android)** • 💻 **Windows Desktop Popups** • 📧 **Gmail Alerts**  
> 🛡️ **100% Safe:** No university passwords needed. Uses official public class browsing.

---

## 📥 Quick 1-Click Download (No Python Needed!)

Click the button below to download the Windows App:

[![Download Windows Installer](https://img.shields.io/badge/📥_Download_Windows_Installer-Click_Here_(.exe)-2ea44f?style=for-the-badge&logo=windows)](https://github.com/IamOumarIbrahim/class-watcher-uos/releases/download/v1.0.0/UoS-Course-Seat-Monitor-Setup.exe)

👉 **[Direct Download: UoS-Course-Seat-Monitor-Setup.exe (12.9 MB)](https://github.com/IamOumarIbrahim/class-watcher-uos/releases/download/v1.0.0/UoS-Course-Seat-Monitor-Setup.exe)**

---

## 📖 Super Easy 3-Step Setup Guide

Follow these 3 simple steps to start watching your classes:

### 1️⃣ Step 1: Install the App
1. Download `UoS-Course-Seat-Monitor-Setup.exe` from the link above.
2. Double-click to install (just click *Next -> Next -> Finish*).
3. Open **UoS Course Seat Monitor** from your Desktop or Start Menu.

---

### 2️⃣ Step 2: Set Up Phone Alerts (Takes 30 Seconds!)
To get push notifications straight to your phone when a seat opens:

1. On your phone, install the free **ntfy** app:
   - [📱 Download for iPhone (Apple App Store)](https://apps.apple.com/us/app/ntfy/id1625396347)
   - [📱 Download for Android (Google Play Store)](https://play.google.com/store/apps/details?id=io.heckel.ntfy)
2. Open the **ntfy** app on your phone, tap **+ (Add Topic)**, and type any secret name you like (e.g. `uos-student-alerts-77`).
3. In the Windows monitor app, type that exact same name in the **"ntfy Topic Name"** box.
4. *(Optional)* If you also want email notifications, check **"Enable Gmail Alerts"** and enter your Gmail address.

---

### 3️⃣ Step 3: Enter Course CRNs & Click Start!
1. Type the **5-digit CRNs** of the classes you want to watch (e.g. `12091`, `12126`).
2. Type a course label next to each (e.g. `MICRO-LEC`, `NETSEC`).
3. Click **"🔔 Test Alerts"** — your phone and computer will instantly ring with a test notification!
4. Click **"▶ Start Monitoring"**.
5. **Keep your computer plugged in, awake, and connected to WiFi!** That's it! 🎉

---

## ❓ Frequently Asked Questions (FAQ)

<details>
<summary><b>1. What is a CRN and where do I find it?</b></summary>
<br>
A CRN is the 5-digit Course Reference Number (for example: <code>12091</code>, <code>12011</code>). You can find it on the UoS Banner course registration page right next to the section title.
</details>

<details>
<summary><b>2. Do I need to give my University / Microsoft password?</b></summary>
<br>
<b>NO!</b> Never share your password. This monitor checks public course availability and does not require your student login.
</details>

<details>
<summary><b>3. Will this app register the class for me automatically?</b></summary>
<br>
<b>NO.</b> University regulations strictly forbid automated bot registration. This app is a <b>notification tool only</b> — it immediately alerts your phone the millisecond a seat drops so you can open Banner and register the seat yourself before anyone else.
</details>

<details>
<summary><b>4. Does my laptop need to stay on?</b></summary>
<br>
<b>YES.</b> The app continuously checks the system every 30 seconds. Keep your laptop plugged into power, prevent it from going to sleep (keep the lid open or adjust Windows sleep settings), and connected to the internet.
</details>

<details>
<summary><b>5. How do I stop tracking a class once I register it?</b></summary>
<br>
Simply delete its CRN from the box in the app, or replace it with another course you need, and click <b>"💾 Save Settings"</b>!
</details>

---

## 💻 For Developers / Running from Source Code

If you prefer to run from Python source:

```powershell
# 1. Clone the repository
git clone https://github.com/IamOumarIbrahim/class-watcher-uos.git
cd class-watcher-uos/uos-seat-monitor

# 2. Setup virtual environment
.\install.ps1

# 3. Run the GUI
.\run_gui.ps1

# (Or run via command line)
.\.venv\Scripts\python.exe monitor.py
```
