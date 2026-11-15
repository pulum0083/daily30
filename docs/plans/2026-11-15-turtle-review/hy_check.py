# 섞은 방식 결과가 한 해에 기대는지 — 2025년을 빼고, 앞 절반·뒤 절반으로 나눠 다시 본다
import sys, runpy
sys.argv = ["hy_bt.py", "sp500"]
import io, contextlib
buf = io.StringIO()
with contextlib.redirect_stdout(buf):
    g = runpy.run_path("hy_bt.py")
sim = g["sim"]
for name, (sk, ek) in (("섞은 방식", ("kq", "lo20")), ("터틀만", ("t55", "lo20")), ("아무 날", ("rand", "lo20"))):
    T = sim(sk, ek); T["y"] = T.d.dt.year
    a = T[T.y != 2025].R.mean(); e = T[T.y <= 2020].R.mean(); l = T[T.y >= 2021].R.mean()
    print(f"{name}: 2025 빼면 {a:+.2f}R · 2016~2020 {e:+.2f}R · 2021~2026 {l:+.2f}R · 2025 비중 {(T.y == 2025).mean():.0%}")
