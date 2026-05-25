import os
import threading
import tkinter as tk
from tkinter import filedialog, messagebox
from PyPDF2 import PdfReader


# ================== KIỂM TRA KHỔ GIẤY =====================
def detect_page_size(page):
    try:
        box = page.mediabox
        w = float(box.width)
        h = float(box.height)
        w2, h2 = w, h  # giữ lại bản gốc để kiểm tra landscape
        w, h = sorted([w, h])  # short, long
    except:
        return "OTHER"

    # ----- A4 (≈ 595 × 842) -----
    if 580 <= w <= 610 and 820 <= h <= 870:
        return "A4"

    # ----- A3 (≈ 842 × 1191) -----
    if 820 <= w <= 870 and 1170 <= h <= 1220:
        return "A3"

    # =====================================================
    #  ⏬ TRƯỜNG HỢP NGOẠI CỠ — NẾU LANDSCAPE → TÍNH LÀ A3
    # =====================================================
    # landscape nghĩa là chiều ngang > chiều dọc
    if w2 > h2:  
        return "A3"

    return "OTHER"


# ================== HÀM ĐẾM PDF =====================
def count_pdf_pages_realtime(folder, update_callback, done_callback):
    total_files = 0
    total_pages = 0
    total_a4 = 0
    total_a3 = 0
    total_other = 0

    for root, dirs, files in os.walk(folder):
        for f in files:
            if f.lower().endswith(".pdf"):
                total_files += 1
                pdf_path = os.path.join(root, f)

                try:
                    reader = PdfReader(pdf_path)
                    for page in reader.pages:
                        total_pages += 1

                        size = detect_page_size(page)
                        if size == "A4":
                            total_a4 += 1
                        elif size == "A3":
                            total_a3 += 1
                        else:
                            total_other += 1

                except Exception as e:
                    print("Lỗi đọc PDF:", pdf_path, e)

                # Cập nhật giao diện realtime
                update_callback(total_files, total_pages, total_a4, total_a3, total_other)

    done_callback(total_files, total_pages, total_a4, total_a3, total_other)


# ================== XUẤT TXT =====================
def export_to_txt(folder, total_files, total_pages, total_a4, total_a3, total_other):
    save_path = filedialog.asksaveasfilename(
        initialfile="thong_ke_pdf.txt",
        defaultextension=".txt",
        filetypes=[("Text files", "*.txt")]
    )
    if not save_path:
        return

    with open(save_path, "w", encoding="utf-8") as f:
        f.write(f"Thư mục: {folder}\n")
        f.write(f"Tổng số file PDF: {total_files}\n")
        f.write(f"Tổng số trang PDF: {total_pages}\n")
        f.write(f"Trang A4: {total_a4}\n")
        f.write(f"Trang A3: {total_a3}\n")
        f.write(f"Trang khác: {total_other}\n")

    messagebox.showinfo("Xong", f"Đã lưu file:\n{save_path}")


# ================== CHỌN THƯ MỤC =====================
def select_folder():
    folder = filedialog.askdirectory()
    if folder:
        lbl_folder.config(text=folder)
        btn_start.config(state="normal")


# ================== NÚT BẮT ĐẦU =====================
def start_counting():
    folder = lbl_folder.cget("text")
    if folder == "(Chưa chọn thư mục)":
        messagebox.showwarning("Thông báo", "Bạn chưa chọn thư mục!")
        return

    btn_start.config(state="disabled")

    t = threading.Thread(
        target=count_pdf_pages_realtime,
        args=(folder, update_realtime, count_done)
    )
    t.daemon = True
    t.start()


# ================== CALLBACK REALTIME =====================
def update_realtime(files, pages, a4, a3, other):
    lbl_files.config(text=f"Tổng PDF: {files}")
    lbl_pages.config(text=f"Tổng trang: {pages}")
    lbl_a4.config(text=f"A4: {a4}")
    lbl_a3.config(text=f"A3: {a3}")
    lbl_other.config(text=f"Khác: {other}")


# ================== CALLBACK HOÀN TẤT =====================
def count_done(files, pages, a4, a3, other):
    btn_start.config(state="normal")
    messagebox.showinfo("Thông báo", "Đã quét xong!")

    export_to_txt(
        lbl_folder.cget("text"),
        files, pages, a4, a3, other
    )


# ================== GUI =====================
window = tk.Tk()
window.title("Thống kê PDF (đa luồng + A4/A3)")
window.geometry("650x380")

tk.Label(window, text="Thống kê PDF theo khổ giấy", font=("Arial", 14)).pack(pady=10)

btn_folder = tk.Button(window, text="Chọn thư mục", font=("Arial", 12), command=select_folder)
btn_folder.pack(pady=5)

lbl_folder = tk.Label(window, text="(Chưa chọn thư mục)", fg="blue", font=("Arial", 11))
lbl_folder.pack(pady=5)

btn_start = tk.Button(window, text="Bắt đầu đếm", font=("Arial", 12), state="disabled", command=start_counting)
btn_start.pack(pady=10)

lbl_files = tk.Label(window, text="Tổng PDF: 0", font=("Arial", 12))
lbl_files.pack()

lbl_pages = tk.Label(window, text="Tổng trang: 0", font=("Arial", 12))
lbl_pages.pack()

lbl_a4 = tk.Label(window, text="A4: 0", font=("Arial", 12))
lbl_a4.pack()

lbl_a3 = tk.Label(window, text="A3: 0", font=("Arial", 12))
lbl_a3.pack()

lbl_other = tk.Label(window, text="Khác: 0", font=("Arial", 12))
lbl_other.pack()

window.mainloop()
