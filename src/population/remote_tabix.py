"""Minimal remote tabix reader (TBI index + BGZF blocks over HTTP range requests).

Lets us read just the compressed blocks of a huge public bgzipped VCF that contain a region, instead of
downloading the file (gnomAD v4.1 exome chr1 alone is ~18.8 GB). Pure Python (no pysam, which has no Windows
build). Implements the tabix spec: bin/chunk index + 16 kb linear index, BGZF block framing.
"""
import gzip
import struct
import threading
import zlib
from typing import Dict, List, Tuple

import requests

BLOCK_PAD = 70000          # a BGZF block is <= 64 KiB, read past the last chunk offset to include it fully


def _reg2bins(beg: int, end: int) -> List[int]:
    end -= 1
    bins = [0]
    for shift, off in ((26, 1), (23, 9), (20, 73), (17, 585), (14, 4681)):
        bins.extend(range(off + (beg >> shift), off + (end >> shift) + 1))
    return bins


class RemoteTabix:
    def __init__(self, url: str, session: requests.Session = None):
        self.url = url
        self.s = session or requests.Session()
        self.s.headers["User-Agent"] = "rare-disease-assistant-research/1.0 (academic prototype)"
        self.bytes_read = 0
        self._lock = threading.Lock()
        idx = gzip.decompress(self._get(url + ".tbi"))
        if idx[:4] != b"TBI\x01":
            raise ValueError("not a tabix index")
        n_ref, fmt, col_seq, col_beg, col_end, meta, skip, l_nm = struct.unpack("<8i", idx[4:36])
        names = idx[36:36 + l_nm].split(b"\x00")[:n_ref]
        p = 36 + l_nm
        self.refs: Dict[str, Tuple[dict, list]] = {}
        for name in names:
            (n_bin,) = struct.unpack("<i", idx[p:p + 4]); p += 4
            bins = {}
            for _ in range(n_bin):
                b, n_chunk = struct.unpack("<Ii", idx[p:p + 8]); p += 8
                chunks = [struct.unpack("<QQ", idx[p + 16 * i:p + 16 * i + 16]) for i in range(n_chunk)]
                p += 16 * n_chunk
                bins[b] = chunks
            (n_intv,) = struct.unpack("<i", idx[p:p + 4]); p += 4
            ioff = list(struct.unpack(f"<{n_intv}Q", idx[p:p + 8 * n_intv])); p += 8 * n_intv
            self.refs[name.decode()] = (bins, ioff)

    def _get(self, url, rng=None) -> bytes:
        last = None
        for attempt in range(4):
            try:
                r = self.s.get(url, headers={"Range": f"bytes={rng[0]}-{rng[1]}"} if rng else {}, timeout=120)
                if r.status_code in (200, 206):
                    with self._lock:
                        self.bytes_read += len(r.content)
                    return r.content
                last = f"HTTP {r.status_code}"
            except requests.RequestException as e:
                last = type(e).__name__
        raise ConnectionError(f"range read failed: {last}")

    def chunks_for(self, chrom: str, beg0: int, end0: int) -> List[Tuple[int, int]]:
        if chrom not in self.refs:
            return []
        bins, ioff = self.refs[chrom]
        min_off = ioff[beg0 >> 14] if (beg0 >> 14) < len(ioff) else (ioff[-1] if ioff else 0)
        chunks = [c for b in _reg2bins(beg0, end0) for c in bins.get(b, []) if c[1] > min_off]
        chunks.sort()
        merged: List[List[int]] = []
        for b, e in chunks:
            b = max(b, min_off)
            if merged and b <= merged[-1][1]:
                merged[-1][1] = max(merged[-1][1], e)
            else:
                merged.append([b, e])
        return [(b, e) for b, e in merged]

    def estimate_bytes(self, chrom: str, beg0: int, end0: int) -> int:
        """Upper bound of compressed bytes needed for a region, from the index alone (no data read)."""
        return sum(((e >> 16) - (b >> 16)) + 65536 for b, e in self.chunks_for(chrom, beg0, end0))

    def fetch_lines(self, chrom: str, beg1: int, end1: int) -> List[str]:
        """VCF lines whose POS lies in [beg1, end1] (1-based, inclusive)."""
        out = []
        for vb, ve in self.chunks_for(chrom, beg1 - 1, end1):
            cb, ub, ce, ue = vb >> 16, vb & 0xFFFF, ve >> 16, ve & 0xFFFF
            data = self._get(self.url, (cb, ce + BLOCK_PAD))
            text, i, upto = [], 0, None
            consumed = 0
            while i + 18 <= len(data):
                if data[i:i + 2] != b"\x1f\x8b":
                    break
                xlen = struct.unpack("<H", data[i + 10:i + 12])[0]
                bsize = struct.unpack("<H", data[i + 16:i + 18])[0] + 1
                if i + bsize > len(data):
                    break
                coff = cb + i
                if coff > ce:
                    break
                blk = zlib.decompress(data[i + 12 + xlen:i + bsize - 8], -15)
                if coff == ce:
                    upto = consumed + ue
                text.append(blk)
                consumed += len(blk)
                i += bsize
            raw = b"".join(text)
            raw = raw[ub:(upto if upto is not None else len(raw))]
            for line in raw.split(b"\n"):
                if not line or line.startswith(b"#"):
                    continue
                f = line.split(b"\t", 8)
                pos = int(f[1])
                if beg1 <= pos <= end1:
                    out.append(line.decode("latin1"))
        return out


# ---------------------------------------------------------------------------------------------------------
# Block-level seeking: read only the BGZF blocks around a region instead of a whole tabix bin chunk.
# ---------------------------------------------------------------------------------------------------------
_MAGIC = b"\x1f\x8b\x08\x04\x00\x00\x00\x00\x00\xff\x06\x00BC\x02\x00"


def _decode_blocks(data: bytes, base: int):
    """Decode complete BGZF blocks in `data` (which starts at file offset `base`) beginning at the first block magic.
    Returns list of (block_file_offset, uncompressed_bytes)."""
    i = data.find(_MAGIC)
    out = []
    while i >= 0 and i + 18 <= len(data):
        if data[i:i + 2] != b"\x1f\x8b":
            break
        xlen = struct.unpack("<H", data[i + 10:i + 12])[0]
        bsize = struct.unpack("<H", data[i + 16:i + 18])[0] + 1
        if i + bsize > len(data):
            break
        out.append((base + i, zlib.decompress(data[i + 12 + xlen:i + bsize - 8], -15)))
        i += bsize
    return out


def _first_full_line_pos(blocks):
    raw = b"".join(b for _, b in blocks)
    nl = raw.find(b"\n")
    if nl < 0:
        return None
    nxt = raw.find(b"\n", nl + 1)
    if nxt < 0:
        return None
    return int(raw[nl + 1:nxt].split(b"\t", 2)[1])


def fetch_lines_seek(self, chrom: str, beg1: int, end1: int, probe_bytes=90000, stream_bytes=400000):
    """Same result as fetch_lines, but binary-searches the compressed blocks of each chunk first."""
    out = []
    for vb, ve in self.chunks_for(chrom, beg1 - 1, end1):
        cb, ub, ce = vb >> 16, vb & 0xFFFF, ve >> 16
        if ce - cb < 600000:                      # small chunk: plain read is cheaper than probing
            out.extend(self._lines_from(cb, ub, ce, beg1, end1, first=True))
            continue
        lo, hi = cb, ce
        while hi - lo > 150000:
            mid = (lo + hi) // 2
            blocks = _decode_blocks(self._get(self.url, (mid, mid + probe_bytes)), mid)
            pos = _first_full_line_pos(blocks[:2]) if blocks else None
            if pos is None:
                hi = mid
            elif pos < beg1:
                lo = blocks[0][0]
            else:
                hi = mid
        start = max(cb, lo - 70000)               # back off one block so a line straddling the boundary is not missed
        out.extend(self._lines_from(start, ub if start == cb else None, ce, beg1, end1, first=(start == cb)))
    return out


def _lines_from(self, start: int, ubeg, ce: int, beg1: int, end1: int, first: bool, stream_bytes=400000):
    off, carry, lines, pending = start, b"", [], True
    skipped_partial = first
    while pending and off <= ce + 1:
        data = self._get(self.url, (off, off + stream_bytes - 1))
        blocks = _decode_blocks(data, off)
        if not blocks:
            break
        raw = carry
        for i, (boff, blk) in enumerate(blocks):
            if i == 0 and first and ubeg:
                blk = blk[ubeg:]
            raw += blk
        first = False
        if not skipped_partial:                      # mid-file start: drop the partial first line
            nl = raw.find(b"\n")
            raw = raw[nl + 1:] if nl >= 0 else b""
            skipped_partial = True
        last_nl = raw.rfind(b"\n")
        body, carry = (raw[:last_nl + 1], raw[last_nl + 1:]) if last_nl >= 0 else (b"", raw)
        for line in body.split(b"\n"):
            if not line or line.startswith(b"#"):
                continue
            pos = int(line.split(b"\t", 2)[1])
            if pos > end1:
                pending = False
                break
            if pos >= beg1:
                lines.append(line.decode("latin1"))
        last_off = blocks[-1][0]
        next_off = last_off + (struct.unpack("<H", data[last_off - off + 16:last_off - off + 18])[0] + 1)
        if next_off > ce or next_off <= off:
            break
        off = next_off
    return lines


RemoteTabix.fetch_lines_seek = fetch_lines_seek
RemoteTabix._lines_from = _lines_from
