# us_detail_data 순수 계산함수 단위 테스트 (네트워크 없음)
#!/usr/bin/env python3
"""실행: python3 scripts/test_us_detail_data.py"""
import us_detail_data as u


def test_fmt_usd():
    assert u.fmt_usd(81_615_000_000.0) == "$81.6B"
    assert u.fmt_usd(1_230_000_000.0) == "$1.23B"
    assert u.fmt_usd(543_000_000.0) == "$543M"
    assert u.fmt_usd(-1_200_000_000.0) == "−$1.20B"
    assert u.fmt_usd(None) == ""


def run():
    fns = [v for k, v in globals().items() if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ✓ {fn.__name__}")
    print(f"{len(fns)} passed")


if __name__ == "__main__":
    run()
