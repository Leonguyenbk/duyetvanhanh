import os
import re

folder = r"G:\My Drive\Congviec\TOKSNV\KH2959\NHOM1\TANAN\DK Tan An.daky"  # sửa đường dẫn folder

prefix = "CHUACOGIAY_24163"

files = [f for f in os.listdir(folder) if f.lower().endswith(".pdf")]

def get_last_number(filename):
    name = os.path.splitext(filename)[0]

    # Xóa _0001 cuối nếu có
    name = re.sub(r"_\d{4}$", "", name)

    nums = re.findall(r"\d+", name)
    return int(nums[-1]) if nums else None

data = []
for f in files:
    n = get_last_number(f)
    if n is not None:
        data.append((f, n))

if not data:
    print("Không tìm thấy file PDF có số cuối.")
    raise SystemExit

# Sắp theo số cuối: 30,31,32... hoặc 1-30, 31-60...
data.sort(key=lambda x: x[1])

# đổi tên tạm tránh trùng
temp_paths = []
for i, (old_name, _) in enumerate(data):
    old_path = os.path.join(folder, old_name)
    temp_path = os.path.join(folder, f"__temp_rename_{i}.pdf")
    os.rename(old_path, temp_path)
    temp_paths.append(temp_path)

# đánh lại từ 1
for idx, temp_path in enumerate(temp_paths, start=1):
    new_name = f"{prefix}_{idx}-GT.pdf"
    new_path = os.path.join(folder, new_name)
    os.rename(temp_path, new_path)
    print(f"{os.path.basename(temp_path)} -> {new_name}")

print("Đã đổi tên xong.")