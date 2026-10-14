# TVTruyen crawler (Python)

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
python crawler.py https://www.tvtruyen.space/sieu-nang-luc-ta-co-mot-chiec-guong-sao-chep.html --max-chapters 2
```

Tải các chương tìm được của một truyện:

```sh
python crawler.py https://www.tvtruyen.space/chong-lay-tien-cho-gai.html
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
