"""
Tool Tự Động Duyệt Vận Hành - Đắk Lắk (refactored, cleaned up)
All utility functions are now in duyet_helpers module to eliminate duplication.
"""

import tkinter as tk
from tkinter import ttk

from duyet_helpers import (
    browse_folder,
    start_automation_thread,
)


def create_gui():
    """Create and run the main GUI."""
    root = tk.Tk()
    root.title("Tool Tự Động Duyệt Vận Hành - Đắk Lắk")

    frame = ttk.Frame(root, padding="20")
    frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))

    ttk.Label(frame, text="Username:").grid(column=0, row=0, sticky=tk.W, pady=5)

    username_entry = ttk.Entry(frame, width=45)
    username_entry.grid(column=1, row=0, sticky=(tk.W, tk.E), columnspan=2)

    ttk.Label(frame, text="Password:").grid(column=0, row=1, sticky=tk.W, pady=5)

    password_entry = ttk.Entry(frame, show="*", width=45)
    password_entry.grid(column=1, row=1, sticky=(tk.W, tk.E), columnspan=2)

    ttk.Label(frame, text="Mã xã/phường:").grid(column=0, row=2, sticky=tk.W, pady=5)

    maxa_entry = ttk.Entry(frame, width=45)
    maxa_entry.grid(column=1, row=2, sticky=(tk.W, tk.E), columnspan=2)

    ttk.Label(frame, text="Folder PDF:").grid(column=0, row=3, sticky=tk.W, pady=5)

    folder_var = tk.StringVar()

    folder_entry = ttk.Entry(frame, textvariable=folder_var, width=45)
    folder_entry.grid(column=1, row=3, sticky=(tk.W, tk.E))

    btn_browse = ttk.Button(
        frame,
        text="Chọn folder",
        command=lambda: browse_folder(folder_var),
    )

    btn_browse.grid(column=2, row=3, padx=5)

    start_button = ttk.Button(
        frame,
        text="Bắt đầu",
        command=lambda: start_automation_thread(
            username_entry.get().strip(),
            password_entry.get().strip(),
            maxa_entry.get().strip(),
            folder_var.get().strip(),
        ),
    )

    start_button.grid(column=0, row=4, columnspan=3, pady=20)

    ttk.Label(
        frame,
        text="URL cố định: https://dla.mplis.gov.vn/dc/ThuThapThongTin",
    ).grid(column=0, row=5, columnspan=3, sticky=tk.W, pady=5)

    root.columnconfigure(0, weight=1)
    root.rowconfigure(0, weight=1)
    frame.columnconfigure(1, weight=1)

    root.mainloop()


if __name__ == "__main__":
    create_gui()
