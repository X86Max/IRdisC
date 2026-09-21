"""Terminal-cell-aware clipping and wrapping, without optional dependencies."""
import re
import unicodedata


def cell_width(char):
    if unicodedata.combining(char) or unicodedata.category(char) in ('Mn', 'Me', 'Cf'):
        return 0
    return 2 if unicodedata.east_asian_width(char) in ('W', 'F') else 1


def cells(text):
    return sum(cell_width(char) for char in text)


def clip(text, width):
    used = 0
    end = 0
    for i, char in enumerate(text):
        used += cell_width(char)
        if used > max(0, width):
            break
        end = i+1
    return text[:end]


def wrap_cells(text, width, indent=0):
    """Return (visual text, source offset), breaking long tokens without hyphens."""
    width = max(1, width)
    indent = max(0, min(indent, width//2))
    rows = []
    start = 0
    while start < len(text):
        pad = ' ' * (indent if rows else 0)
        piece = clip(text[start:], width-len(pad))
        if not piece:  # A wide glyph cannot fit in a single-column viewport.
            piece = '?'
            end = start+1
        else:
            end = start+len(piece)
        if end < len(text) and not text[end].isspace():
            space = piece.rfind(' ')
            if space > 0:
                end = start+space+1
                piece = text[start:end]
        rows.append((pad+piece.rstrip(), start))
        start = end
        while start < len(text) and text[start].isspace():
            start += 1
    return rows or [('', 0)]


def message_rows(text, width):
    match = re.match(r'^\d\d:\d\d  (?:<[^>]+> |\* \S+ )?', text)
    indent = cells(match.group()) if match else 0
    # Normal prefixes align exactly; unusually long nicks get their own line.
    if match and indent >= width//2 and indent < width:
        prefix = match.group()
        return [(prefix.rstrip(), 0)] + [(line, offset+len(prefix))
                                        for line, offset in wrap_cells(text[len(prefix):], width)]
    return wrap_cells(text, width, indent)
