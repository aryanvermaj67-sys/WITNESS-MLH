"""Builds small text PDFs in memory for the tests (no extra library)."""


def _esc(line: str) -> str:
    return line.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def make_pdf(pages: list[list[str]]) -> bytes:
    """One PDF page per entry; each entry is a list of text lines, so a test can imitate hard-wrapped PDF text."""
    n = len(pages)
    objs = [b"<< /Type /Catalog /Pages 2 0 R >>",
            f"<< /Type /Pages /Kids [{' '.join(f'{4 + 2 * i} 0 R' for i in range(n))}] /Count {n} >>".encode(),
            b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"]
    for i, lines in enumerate(pages):
        content = f"{5 + 2 * i} 0 R"
        objs.append((f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents {content} "
                     "/Resources << /Font << /F1 3 0 R >> >> >>").encode())
        stream = "BT /F1 11 Tf 72 740 Td 14 TL " + " ".join(f"({_esc(line)}) Tj T*" for line in lines) + " ET"
        objs.append(f"<< /Length {len(stream)} >>\nstream\n{stream}\nendstream".encode("latin-1"))
    out, offsets = b"%PDF-1.4\n", []
    for number, body in enumerate(objs, 1):
        offsets.append(len(out))
        out += f"{number} 0 obj\n".encode() + body + b"\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objs) + 1}\n0000000000 65535 f \n".encode()
    out += b"".join(f"{offset:010d} 00000 n \n".encode() for offset in offsets)
    return out + f"trailer\n<< /Size {len(objs) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()


# a small "handbook" with wrapped lines, a heading, and a word split across two lines
HANDBOOK = [
    ["Project Alpha Handbook",
     "Teams may have up to five members and every member must be at",
     "least sixteen years old. The final report is due on Friday at",
     "noon. Late reports are not accepted under any circum-",
     "stances."],
    ["Prizes",
     "The winning team receives a trophy and a cash award of two",
     "hundred dollars. Runners up receive a certificate."],
]
