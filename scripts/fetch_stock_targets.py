# 네이버 증권사 리포트에서 종목별 목표주가·투자의견을 수집해 컨센서스를 계산하는 스크립트
import re
import urllib.request

UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"}
LIST_URL = ("https://finance.naver.com/research/company_list.naver"
            "?searchType=itemCode&itemCode={code}&page={page}")
DETAIL_URL = "https://finance.naver.com/research/company_read.naver?nid={nid}&page=1"

_STRIP = re.compile(r"<[^>]+>")


def _text(html):
    return _STRIP.sub("", html).strip()


def fetch_euckr(url):
    """네이버 금융 리서치 게시판은 EUC-KR로 서빙된다."""
    req = urllib.request.Request(url, headers=UA)
    return urllib.request.urlopen(req, timeout=20).read().decode("euc-kr", "ignore")


def parse_report_list(html):
    """목록 HTML에서 (증권사, 날짜, nid)를 뽑는다. 목표가는 목록에 없다."""
    out = []
    for row in re.findall(r"<tr[^>]*>(.*?)</tr>", html, re.S):
        nid = re.search(r"nid=(\d+)", row)
        cols = [_text(c) for c in re.findall(r"<td[^>]*>(.*?)</td>", row, re.S)]
        cols = [c for c in cols if c]
        if not nid or len(cols) < 4:
            continue
        if not re.fullmatch(r"\d{2}\.\d{2}\.\d{2}", cols[3]):
            continue
        out.append({"firm": cols[2], "date": cols[3], "nid": nid.group(1)})
    return out


def parse_report_detail(html):
    """상세 HTML에서 목표가·투자의견을 뽑는다. 목표가가 없는 리포트는 None."""
    tp = re.search(r"목표가[\s\S]{0,40}?([\d][\d,]{2,})", html)
    op = re.search(r"투자의견\s*<em[^>]*>([^<]+)</em>", html)
    return {
        "target_price": int(tp.group(1).replace(",", "")) if tp else None,
        "opinion": op.group(1).strip() if op else None,
    }
