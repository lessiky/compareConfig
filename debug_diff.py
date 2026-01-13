import difflib

# 模拟场景：内容不同但 diff 为空
content_crlf = "server_name example.com;\r\nlisten 80;"
content_lf = "server_name example.com;\nlisten 80;"

print(f"Content match: {content_crlf == content_lf}")

lines_crlf = content_crlf.splitlines()
lines_lf = content_lf.splitlines()

print(f"Lines match: {lines_crlf == lines_lf}")

diff = difflib.unified_diff(
    lines_lf,
    lines_crlf,
    fromfile='LF',
    tofile='CRLF',
    lineterm=''
)
diff_list = list(diff)
print(f"Diff lines count: {len(diff_list)}")
print("Diff content:")
print('\n'.join(diff_list))
