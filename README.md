# Crawl truyện bằng Python

## Royal Road

File `royalroad.py` nhận URL một truyện, lấy metadata, mục lục và nội dung chương
công khai. Dùng chung môi trường Python và dependencies ở phần cài đặt bên dưới.

```sh
.venv/bin/python royalroad.py https://www.royalroad.com/fiction/21220/mother-of-learning --max-chapters 2
```

Bỏ `--max-chapters 2` để tải toàn bộ chương trong mục lục. Chạy lại cùng lệnh để
tiếp tục từ cache; chương lỗi sẽ được thử lại. Thêm `--refresh` để tải lại các
chương đã lưu. `--max-chapters` tính cả chương đọc từ cache.

```sh
.venv/bin/python royalroad.py https://www.royalroad.com/fiction/21220/mother-of-learning --delay 3 --timeout 30 --retries 3 --output data/royalroad
```

Kết quả nằm trong `data/royalroad/<fiction-id>/`:

- `metadata.json`: tên, tác giả, mô tả, tags, trạng thái và URL ảnh bìa.
- `toc.json`: các chương theo thứ tự xuất hiện trong bảng mục lục, kèm ngày đăng nếu có.
- `chapter-<id>.json`: nội dung từng chương, URL và thời điểm tải.
- `story.json`, `story.txt`: tổng hợp các chương được chọn trong lần chạy hiện tại.
- `progress.json`: số chương đã lưu, lỗi và trạng thái hoàn tất.

Tool kiểm tra robots.txt trước khi lấy dữ liệu, cách mỗi request ít nhất 3 giây
mặc định, retry lỗi kết nối/429/5xx và tôn trọng Retry-After tối đa 300 giây
(server yêu cầu lâu hơn thì dừng để chạy lại sau). HTTP 401/403 hoặc CAPTCHA
sẽ dừng toàn bộ lần chạy. Không đăng nhập, giải CAPTCHA hoặc vượt chặn.
Nếu bị chặn trước khi lấy được metadata, chỉ có thông báo lỗi trên terminal.
Chỉ tải và sử dụng nội dung bạn có quyền truy cập và sử dụng.

`complete: true` nghĩa là đã lưu đủ các chương xuất hiện trong mục lục HTML của
lần chạy; không bao gồm chương đã gỡ hoặc không công khai. Khi giới hạn số chương,
file tổng hợp chỉ chứa phần được chọn; cache của các chương khác vẫn được giữ.
Chương đã lưu mặc định không được kiểm tra lại xem có sửa hoặc gỡ khỏi website.

**Tình trạng kiểm chứng:** Đã kiểm tra trang truyện và robots.txt qua công cụ web.
Request HTML trực tiếp từ môi trường phát triển nhận HTTP 403, nên chưa xác nhận
được chạy end-to-end với Royal Road. Bộ test dùng HTML mẫu; selector có thể cần
điều chỉnh nếu giao diện website thay đổi. Không cam kết lấy đủ nội dung khi mục
lục phân trang hoặc được tải động. Bộ trích xuất bỏ các phần ẩn bằng markup/CSS
đơn giản, không chạy JavaScript hay dựng đầy đủ layout trình duyệt.

Kiểm tra cả hai crawler:

```sh
.venv/bin/python -m unittest -v
```

## TVTruyen

Crawl metadata và nội dung chương công khai từ <https://www.tvtruyen.space>.
Python 3.10 trở lên, không cần trình duyệt.

## Cài đặt

```sh
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Chạy

Thử hai chương trước:

```sh
python crawler.py https://www.tvtruyen.space/chang-re-manh-nhat-lich-su.html --max-chapters 1169
```

Tải các chương tìm được của một truyện:

```sh
python crawler.py https://www.tvtruyen.space/dinh-phong-thien-ha.html
python crawler.py https://www.tvtruyen.space/chang-re-manh-nhat-lich-su.html  
```

Lấy tối đa 5 truyện từ trang danh sách, mỗi truyện tối đa 10 chương:

```sh
python crawler.py https://www.tvtruyen.space/the-loai/tat-ca/truyen-full.html --listing --max-stories 5 --max-chapters 10
```

Các tùy chọn: `--output data`, `--delay 2` (giây), `--timeout 30`,
`--retries 3`, `--max-pages 1`. Phân trang danh sách đi theo liên kết `rel="next"`
nếu có; danh sách truyện gồm các liên kết truyện xuất hiện trên trang, kể cả đề xuất.
`--max-chapters 0` tải toàn bộ chương tìm được.

Chạy lại cùng lệnh và thư mục output để tiếp tục: chương đã lưu được đọc từ cache,
còn metadata được cập nhật. Cache không tự làm mới nội dung chương đã lưu.
Nhấn Ctrl+C để dừng; các chương đã ghi thành công vẫn được giữ.

## Kết quả

Trong `data/<slug>/`:

- `metadata.json`: tên, tác giả, thể loại, trạng thái, mô tả, URL ảnh bìa.
- `chuong-*.json`: URL, tiêu đề, nội dung, URL chương tiếp.
- `progress.json`: số chương đã xét, đã lưu, các lỗi của lần chạy.
- `story.json`: metadata cùng các chương đọc được trong lần chạy.
- `story.txt`: bản văn bản UTF-8 của các chương đó.

Website mẫu có danh sách chương rỗng trong HTML. Khi không tìm thấy liên kết,
tool thử `/chuong-1`, rồi đi theo nút `#next_chap`. Nếu gặp chương lỗi hoặc khóa
và không có liên kết chương khác để tiếp tục, tool dừng chuỗi đó và ghi lỗi.
Vì vậy không đảm bảo thu thập đủ mọi chương nếu website thay đổi cấu trúc,
chương đầu không tồn tại, hoặc chuỗi bị ngắt. `limit_reached: false` chỉ có nghĩa
là đã hết các liên kết tìm được. Tool không đăng nhập hoặc mở khóa chương VIP.

Tool kiểm tra robots.txt, mặc định cách mỗi request 2 giây, retry lỗi kết nối,
429 và 5xx với thời gian chờ tăng dần. Không crawl hàng loạt khi chưa kiểm tra
kết quả mẫu. Exit code 1 báo có lỗi; xem log và `progress.json`.

## Kiểm tra

```sh
python -m unittest -v
```
