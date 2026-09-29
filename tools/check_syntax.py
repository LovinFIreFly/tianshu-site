import re

src = open(r'C:\Users\junbo\Desktop\网站\mobile\app.js', encoding='utf-8').read()

# Naive quote/paren balance check ignoring strings/comments
def strip_strings_and_comments(s):
    # Remove single-line comments
    s = re.sub(r'//[^\n]*', '', s)
    # Remove multi-line comments (non-greedy)
    s = re.sub(r'/\*.*?\*/', '', s, flags=re.DOTALL)
    # Remove string literals (roughly)
    s = re.sub(r'"(?:[^"\\]|\\.)*"', '""', s)
    s = re.sub(r"'(?:[^'\\]|\\.)*'", "''", s)
    # Remove regex literals? ignore for now
    return s

clean = strip_strings_and_comments(src)
for i, line in enumerate(clean.splitlines(), 1):
    # count parens, brackets, braces
    for pair in [('(', ')'), ('[', ']'), ('{', '}')]:
        o, c = pair
        if line.count(o) != line.count(c):
            print(f'Line {i} unbalanced {pair}: {line.count(o)} open {line.count(c)} close')
            print(line)
            print('---')

# Also check for any line with odd quotes after stripping comments
for i, line in enumerate(src.splitlines(), 1):
    # replace escaped quotes with placeholder
    s = re.sub(r'\\"', '', line)
    s = re.sub(r"\\'", '', s)
    if s.count('"') % 2 != 0 or s.count("'") % 2 != 0:
        print(f'Line {i} quote suspicious: {s.count(chr(34))}" {s.count(chr(39))}\' -> {line}')
