<h1 style="font-family:'Syne', sans-serif; font-weight:800;
  color:#fff;">Pi <span style="color:#ffc83d;">Lyrics</span></h1>

A web-based slide management system designed to run smoothly on Raspberry Pi devices like the Zero 2 W, with support for displaying PDF slides on vertical monitors. Ideal for church services, presentations, or any scenario requiring sequential lyric slide playback with remote control capabilities.

## Features

- **Web Interface**: Upload, reorder, rename, and delete PDF slides through a clean web UI
- **Blank Slides**: Insert custom blank slides with labels for transitions or breaks
- **Real-time Display**: Dedicated display application that shows slides on a rotated monitor
- **Remote Control**: Navigate slides via web interface or keyboard shortcuts on the display
- **Optional Authentication**: Secure login system with admin capabilities — or disable it for public access
- **File Management**: Automatic PDF page counting and multi-page support
- **Drag & Drop**: Intuitive reordering of slides via drag-and-drop
- **Responsive Design**: Works on desktop and mobile devices

## Installation

### Prerequisites

- Raspberry Pi OS installed on your Pi device
- Internet connection for downloading packages

### Setup

1. Clone the repository:
   ```bash
   git clone <repository-url>
   cd pi-lyrics
   ```

2. Run the installer:
   ```bash
   sudo bash install.sh
   ```

The installer will:
- install required system packages with `apt`
- create `~/pi-lyrics`
- copy `display.py` and `server.py` into that directory
- create a Python venv with `--system-site-packages`
- install `Flask==2.3.3`, `Werkzeug==3.0.0`, and `pymupdf==1.22.3` in the venv

### Why this is needed

The Pi install can fail in two common ways:
- `low disk space` errors while creating the venv
- `No module named fitz` after installing `python3-pymupdf` from apt

This project works reliably by installing `pymupdf==1.22.3` directly into the venv with a temporary disk-backed `TMPDIR`.

### Manual fallback

If you prefer to do the steps manually, use:
```bash
mkdir -p ~/tmp
TMPDIR=~/tmp python3 -m venv ~/pi-lyrics/venv --system-site-packages
TMPDIR=~/tmp ~/pi-lyrics/venv/bin/python -m pip install --break-system-packages --no-cache-dir \
  "Flask==2.3.3" "Werkzeug==3.0.0" "pymupdf==1.22.3"
```

### Optional autostart

To enable autostart for both the web server and display on boot, run:
```bash
sudo bash enable-autostart.sh
```

This creates:
- A systemd service that starts the web server automatically on system boot
- A desktop entry that starts the display app automatically on desktop login (with a 20-second delay)

If you do not want autostart, simply do not run this script. You can start both services manually anytime:
```bash
bash start-server.sh   # Start web server
bash start-display.sh  # Start display app
```

### Starting the app

After install, start the services manually:

**Web server:**
```bash
bash start-server.sh
```

**Display app:**
```bash
bash start-display.sh
```

**Optional automatic start:**

To enable both services to start automatically on boot:
```bash
sudo bash enable-autostart.sh
```

This sets up systemd for the web server (boots on system start) and desktop autostart for the display app (starts on desktop login).

## Usage

### Web Server

By default, the web server is manual start. To run it:
```bash
bash start-server.sh
```

Or run directly:
```bash
~/pi-lyrics/venv/bin/python ~/pi-lyrics/server.py
```

Access the web interface at `http://localhost:5000`.

**To enable automatic start on system boot:**

Run `sudo bash enable-autostart.sh` to set up the systemd service. After that, the server will start automatically on boot.

To check systemd service status:
```bash
sudo systemctl status pi-lyrics-server.service
sudo systemctl restart pi-lyrics-server.service
```

To view server logs:
```bash
sudo journalctl -u pi-lyrics-server.service --no-pager
```

### Display Application

Start the display app on the Pi monitor:
```bash
bash start-display.sh
```

Or run it manually with:
```bash
DISPLAY=:0 ~/pi-lyrics/venv/bin/python ~/pi-lyrics/display.py &
```

To enable autostart on login:
```bash
bash enable-autostart.sh
```

### Web Interface

The display will automatically connect to the server and show slides in fullscreen mode.

![Pi Lyrics Display](screenshots/display.png)

The rotated display layout is designed for vertical monitors and shows the next slide preview while rendering the current PDF in fullscreen.

#### First-time setup

1. **Setup**: On first run, create an owner account and choose whether to enable login
2. **Login** (if enabled): Use your username and password to access the system

   ![Pi Lyrics Login](screenshots/login.png)

#### Using the dashboard

3. **Upload Slides**: Drag and drop PDF files or click to browse
4. **Reorder Slides**: Drag slides to change their order
5. **Insert Blank Slides**: Click "Blank Slide" to add labeled blank slides
6. **Control Display**: Use Previous/Next buttons to navigate slides remotely
7. **Rename Slides**: Click on any slide name to rename it

The dashboard combines upload, queue management, and display controls into a single unified interface.

![Pi Lyrics Dashboard](screenshots/dashboard.png)

### Keyboard Shortcuts (on Display)

- `→` / `↓` / `Space` — Next page/slide
- `←` / `↑` — Previous page/slide
- `PgDn` / `PgUp` — Also work for navigation

### Admin Panel

Access the admin panel at `http://localhost:5000/admin` (admin users only) to:

- **Manage Users**: Approve user requests, make users admin or regular users, and delete accounts
- **Configure Login**: Enable or disable the login system (owner only) — toggle between requiring authentication or allowing public access
- **Reset App**: Owner-only reset to factory state, removing all slides and user accounts while preserving the app files

The owner account is protected and cannot be deleted.

## Configuration

The application uses several configuration files:

- `order.json`: Stores the current slide order
- `state.json`: Tracks current display state
- `control.json`: Handles remote control commands
- `users.json`: User account data (encrypted)
- `secret.key`: Flask session secret
- `config.json`: Application settings (login system enabled/disabled)

All files are created automatically in the project directory.

### Login System Configuration

On first setup, you'll be prompted to choose whether to enable or disable the login system:

- **Login Enabled** (default): Users must authenticate with username and password. Admin panel accessible at `/admin`.
- **Login Disabled**: Anyone can access the app without authentication. All authentication UI is hidden.

To change this setting anytime, the owner can visit the Admin Panel at `http://localhost:5000/admin` and toggle the "Login System" setting. Disabling login preserves all existing user accounts for future re-enabling.

## API Reference

### Files Management

- `GET /api/files`: Get list of slides
- `POST /api/upload`: Upload new PDF files
- `POST /api/order`: Update slide order
- `DELETE /api/delete/<filename>`: Delete a slide
- `POST /api/rename`: Rename a slide
- `POST /api/blank`: Insert a blank slide

### Display Control

- `GET /api/status`: Get current display status
- `POST /api/control`: Send navigation commands (next/prev)

### Authentication

- `POST /login`: User login
- `POST /register`: Request account access
- `POST /logout`: User logout

## Troubleshooting

### Common Issues

1. **Display not connecting**: Ensure both server and display are running on the same network
2. **PDF not rendering**: Check that PyMuPDF is installed correctly
3. **Permission errors**: Ensure write permissions in the project directory

### Logs

Check the terminal output for error messages and debugging information.

## Development

### Project Structure

```
pi-lyrics/
├── server.py          # Flask web server
├── display.py         # Pygame display application
├── pdfs/              # Uploaded PDF files
├── order.json         # Slide order configuration
├── state.json         # Display state
├── control.json       # Remote control commands
├── users.json         # User accounts
├── config.json        # Application settings (login system)
└── secret.key         # Session secret
```

## License

This project is licensed under the MIT License - see the LICENSE file for details.