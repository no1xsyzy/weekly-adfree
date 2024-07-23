import json
import math
import sys
from datetime import datetime
from functools import cached_property
from hashlib import md5
from io import TextIOWrapper
from os import PathLike
from pathlib import Path
from random import choice
from typing import TypeAlias, Annotated

import jieba
import pandoc
import rich
import typer
from pandoc.types import Pandoc

CanOpen: TypeAlias = PathLike | str | TextIOWrapper


def omni_opener(sth: CanOpen, mode='r', *, encoding='utf-8'):
    if isinstance(sth, (PathLike, str)):
        if str(sth) == '-':
            if 'b' in mode:
                raise TypeError('binary stdin/stdout not supported')
            if 'r' in mode:
                return sys.stdin
            if 'w' in mode:
                return sys.stdout
        return Path(sth).open(mode, encoding=encoding)
    else:
        return sth


class Doc:
    def __init__(self, p: PathLike | str):
        self.path = p
        self._strpath = None
        self._text = None
        self._md5 = None
        self._doc = None
        self._sections = None
        self._plain = None

    @cached_property
    def strpath(self):
        return str(self.path)

    @cached_property
    def text(self):
        with omni_opener(self.path) as f:
            return f.read()

    @cached_property
    def md5(self) -> str:
        return md5(self.text.encode()).hexdigest()

    @cached_property
    def doc(self) -> Pandoc:
        return pandoc.read(self.text, format='gfm')

    @cached_property
    def sections(self) -> list[list]:
        return sections_from_doc(self.doc)

    @cached_property
    def plain(self) -> str:
        return pandoc.write(self.sections, format='plain')

    @cached_property
    def header(self) -> str:
        return pandoc.write(self.sections[0], format='plain').strip()

    def guess(self, spam_filter):
        cut = list(jieba.cut(self.plain))
        return spam_filter.check_spam(cut,
                                      header_word_list=list(jieba.cut(self.header)),
                                      header_impact_multiplier=5.0)


def load_doc(p: CanOpen) -> Pandoc:
    with omni_opener(p) as f:
        return pandoc.read(f.read(), format='gfm')


def all_doc_paths():
    return sorted(Path(f'weekly/docs/').glob('issue-*.md'), key=lambda x: int(x.name[6:-3]))


def load_all() -> list[Pandoc]:
    return [load_doc(p) for p in all_doc_paths()]


def sections_from_doc(doc: Pandoc):
    result = []
    for p in doc[1]:
        if p.__class__.__name__ == 'Header':
            result.append([p])
        else:
            result[-1].append(p)
    return result


class NaiveBayes:
    def __init__(self, counts=None, spams=0, non_spams=0):
        self.counts = {} if counts is None else counts  # c_w_s, c_w_ns
        self.spams = spams
        self.non_spams = non_spams

    @classmethod
    def load(cls, j):
        return cls(**j)

    def dump(self):
        return {'counts': self.counts, 'spams': self.spams, 'non_spams': self.non_spams}

    def mark_spam(self, word_list):
        word_set = set(word_list)
        self.spams += 1
        for w in word_set:
            c = self.counts.setdefault(w, [0, 0])
            c[0] += 1

    def mark_not_spam(self, word_list):
        word_set = set(word_list)
        self.non_spams += 1
        for w in word_set:
            c = self.counts.setdefault(w, [0, 0])
            c[1] += 1

    def check_spam(self, word_list, *, header_word_list=(), header_impact_multiplier=1.):
        word_set = set(word_list)
        header_word_set = set(header_word_list)
        l_ws = len(word_set)
        lmd = 1
        c_s = self.spams
        c_n_s = self.non_spams
        ln_p_ratio = math.log((c_s + lmd) / (c_n_s + lmd))

        for w in word_set:
            c_w_s, c_w_ns = self.counts.get(w, (0, 0))
            impact = math.log(((c_w_s + lmd) / (c_s + lmd * l_ws)) / ((c_w_ns + lmd) / (c_n_s + lmd * l_ws)))
            if w in header_word_set:
                ln_p_ratio += impact * header_impact_multiplier
            else:
                ln_p_ratio += impact
        return ln_p_ratio

    def get_base(self):
        lmd = 1
        c_s = self.spams
        c_n_s = self.non_spams
        return math.log((c_s + lmd) / (c_n_s + lmd))

    def get_impact(self, word):
        c_w_s, c_w_ns = self.counts.get(word, (0, 0))
        lmd = 1
        l_ws = 1
        c_s = self.spams
        c_n_s = self.non_spams
        return math.log(((c_w_s + lmd) / (c_s + lmd * l_ws)) /
                        ((c_w_ns + lmd) / (c_n_s + lmd * l_ws)))

    def print_all_impacts(self):
        lmd = 1
        l_ws = 1
        c_s = self.spams
        c_n_s = self.non_spams
        result = []
        for w, (c_w_s, c_w_ns) in self.counts.items():
            impact = math.log(((c_w_s + lmd) / (c_s + lmd * l_ws)) /
                              ((c_w_ns + lmd) / (c_n_s + lmd * l_ws)))
            result.append([w, impact])
        return result


app = typer.Typer()
nb = NaiveBayes()


def load_nb(fp: CanOpen = 'naive_bayes.json'):
    global nb
    try:
        with omni_opener(fp) as f:
            nb = NaiveBayes.load(json.loads(f.read()))
    except FileNotFoundError:
        pass


def dump_nb(fp: CanOpen = 'naive_bayes.json'):
    with omni_opener(fp, 'w') as f:
        f.write(json.dumps(nb.dump()))


def load_pub_dates():
    try:
        with omni_opener('pub_dates.json') as f:
            return json.load(f)
    except FileNotFoundError:
        return {}


def save_pub_dates(pub_dates):
    with omni_opener('pub_dates.json', 'w') as f:
        json.dump(pub_dates, f)


@app.command()
def train():
    load_nb()

    docs = load_all()

    while True:
        doc = choice(docs)
        sections = sections_from_doc(doc)
        sec = choice(sections)
        plain = pandoc.write(sec, format='plain')
        header = pandoc.write(sec[0], format='plain').strip()
        print(plain)
        cut = list(jieba.cut(plain))
        while (yn := input('spam?(y/n/[q]uit)').lower()) not in ['y', 'n', 'q']:
            pass
        if yn == 'q':
            break
        if yn == 'y':
            nb.mark_spam(cut)
        else:
            nb.mark_not_spam(cut)

        dump_nb()


@app.command()
def check(c: int):
    load_nb()

    doc = load_doc(all_doc_paths()[c])
    for j, sec in enumerate(sections_from_doc(doc)):
        plain = pandoc.write(sec, format='plain')
        header = pandoc.write(sec[0], format='plain').strip()
        cut = list(jieba.cut(plain))
        guess = nb.check_spam(cut, header_word_list=list(jieba.cut(header)),
                              header_impact_multiplier=5.0)
        print(f"[{j}] {header} {guess=}")


@app.command()
def mark(e: int, d: int):
    load_nb()

    doc = load_doc(all_doc_paths()[e])
    sec = sections_from_doc(doc)[d]
    plain = pandoc.write(sec, format='plain')
    print(plain)
    cut = list(jieba.cut(plain))
    while (yn := input('spam?(y/n/[q]uit)').lower()) not in ['y', 'n', 'q']:
        pass
    if yn == 'q':
        return
    if yn == 'y':
        nb.mark_spam(cut)
    else:
        nb.mark_not_spam(cut)

    dump_nb()


@app.command()
def interactive():
    load_nb()

    docs = {}
    doc_paths = all_doc_paths()

    def lc(doc_index):
        doc_index = int(doc_index)
        if doc_index in docs:
            return docs[doc_index]
        docs[doc_index] = load_doc(doc_paths[doc_index])
        return docs[doc_index]

    uses = {}

    while True:
        match input('>').strip().split():
            case ['c', n]:
                doc = lc(n)
                for j, sec in enumerate(sections_from_doc(doc)):
                    plain = pandoc.write(sec, format='plain')
                    header = pandoc.write(sec[0], format='plain').strip()
                    cut = list(jieba.cut(plain))
                    if 'header_impact_multiplier' in uses:
                        guess = nb.check_spam(cut, header_word_list=list(jieba.cut(header)),
                                              header_impact_multiplier=float(uses['header_impact_multiplier']))
                    else:
                        guess = nb.check_spam(cut)

                    if guess >= 5:
                        rich.print(f"\\[{j}] [red]{header}[/] {guess=}")
                    elif guess >= 0:
                        rich.print(f"\\[{j}] [orange_red1]{header}[/] {guess=}")
                    elif guess >= -5:
                        rich.print(f"\\[{j}] [yellow]{header}[/] {guess=}")
                    else:
                        rich.print(f"[{j}] {header} {guess=}")
            case ['m', n, s]:
                doc = lc(n)
                sec = sections_from_doc(doc)[int(s)]
                plain = pandoc.write(sec, format='plain')
                print(plain)
                cut = list(jieba.cut(plain))
                while (yn := input('spam?(y/n/do nothing)').lower()) not in ['y', 'n', 'd']:
                    pass
                if yn == 'd':
                    continue
                if yn == 'y':
                    nb.mark_spam(cut)
                    while nb.check_spam(cut) < 0:
                        nb.mark_spam(cut)
                else:
                    nb.mark_not_spam(cut)
                    while nb.check_spam(cut) > 0:
                        nb.mark_not_spam(cut)

                dump_nb()
            case ['q']:
                return
            case ['p', *words]:
                if not words:
                    print(f'base={nb.get_base()}')
                else:
                    for w in words:
                        print(f'impact({w})={nb.get_impact(w)}')
            case ['j', s]:
                print(jieba.cut(s))
            case ['pj', s]:
                for w in jieba.cut(s):
                    print(f'impact({w})={nb.get_impact(w)}')
            case ['set', s, v]:
                uses[s] = v
            case ['get', s]:
                if s in uses:
                    print(f'{uses[s]=}')
                else:
                    print(f'{s!r} not in uses')
            case ['unset', s]:
                uses.pop(s)
            case [op, *others]:
                print(f'unknown {op=}')


@app.command()
def find_vague():
    load_nb()

    docs = (load_doc(p) for p in all_doc_paths())

    for i, doc in enumerate(docs):
        for j, sec in enumerate(sections_from_doc(doc)):
            plain = pandoc.write(sec, format='plain')
            header = pandoc.write(sec[0], format='plain').strip()
            cut = list(jieba.cut(plain))
            guess = nb.check_spam(cut, header_word_list=list(jieba.cut(header)),
                                  header_impact_multiplier=5.0)
            if abs(guess) < 5:
                print(f"{i} {j} {header} {guess}")


@app.command()
def proc(infile: Annotated[typer.FileText, typer.Argument()] = '-',
         outfile: Annotated[typer.FileTextWrite, typer.Argument()] = '-'):
    load_nb()

    doc = load_doc(infile)
    sections = sections_from_doc(doc)

    filtered_body = []

    for sec in sections:
        plain = pandoc.write(sec, format='plain')
        header = pandoc.write(sec[0], format='plain').strip()
        cut = list(jieba.cut(plain))
        guess = nb.check_spam(cut, header_word_list=list(jieba.cut(header)),
                              header_impact_multiplier=5.0)
        if guess < 0:
            filtered_body.extend(sec)

    result = pandoc.write(Pandoc(doc[0], filtered_body), format='gfm', options=['--wrap=none'])

    outfile.write(result)
    outfile.flush()


def filter_body(sections):
    filtered_body = []

    for sec in sections:
        plain = pandoc.write(sec, format='plain')
        header = pandoc.write(sec[0], format='plain').strip()
        cut = list(jieba.cut(plain))
        guess = nb.check_spam(cut, header_word_list=list(jieba.cut(header)),
                              header_impact_multiplier=5.0)
        if guess < 0:
            filtered_body.extend(sec)

    return filtered_body


@app.command()
def proc_all():
    load_nb()

    pub_dates = load_pub_dates()

    docs = {}

    outdir = Path('docs')

    outdir.mkdir(exist_ok=True)

    changed = False

    last_posts = []

    def last_posts_append(c):
        nonlocal last_posts
        last_posts.append(c)
        last_posts.sort(key=lambda x: x[0], reverse=True)
        last_posts = last_posts[:6]

    for p in all_doc_paths():
        path = str(p)
        doc = docs[path] = Doc(p)
        pub_date, digest = pub_dates.get(path, (None, None))
        path_out = (outdir / p.name)
        if digest == doc.md5:
            last_posts_append((pub_date, path_out, doc))
            continue

        sections = doc.sections

        filtered_body = []

        for sec in sections:
            plain = pandoc.write(sec, format='plain')
            header = pandoc.write(sec[0], format='plain').strip()
            cut = list(jieba.cut(plain))
            guess = nb.check_spam(cut, header_word_list=list(jieba.cut(header)),
                                  header_impact_multiplier=5.0)
            if guess < 0:
                filtered_body.extend(sec)

        p1 = Pandoc(doc.doc[0], filtered_body)
        result = pandoc.write(p1, format='gfm', options=['--wrap=none'])

        path_out.write_text(result, encoding='utf-8')

        changed = True
        pub_date = datetime.now().timestamp()
        digest = doc.md5

        pub_dates[path] = pub_date, digest
        last_posts_append((pub_date, path_out, filtered_body))

    if changed:
        save_pub_dates(pub_dates)

    make_rss(last_posts)


def make_rss(last_posts):
    build_time = datetime.now()
    import email.utils
    project_root = 'https://github.com/no1xsyzy/weekly_adfree'
    with open('rss.xml', 'w', encoding='utf-8') as rss:
        rss.write('<?xml version="1.0" encoding="UTF-8"?>\n')
        rss.write('<rss version="2.0">\n')
        rss.write("  <channel>\n")
        rss.write("    <title>阮一峰的网络日志（免广告版）</title>\n")
        rss.write(f"    <link>{project_root}</link>\n")
        rss.write("    <description>使用朴素贝叶斯筛选器对阮一峰的网络日志进行去广告</description>\n")
        rss.write("    <lang>zh-cn</lang>\n")
        rss.write(f"    <copyright>Copyright {build_time.year}</copyright>\n")
        rss.write(f"    <lastBuildDate>{email.utils.formatdate(build_time.timestamp())}</lastBuildDate>\n")
        for pub_date, path_out, body in last_posts:
            pub_date = email.utils.formatdate(pub_date)
            if isinstance(body, Doc):
                body = filter_body(body.sections)
            rss.write("    <item>\n")
            rss.write(f"      <title>{pandoc.write(body[0], format='plain').strip()}</title>\n")
            rss.write("      <description><![CDATA[")
            rss.write(pandoc.write(body[1:], format='html'))
            rss.write("]]></description>\n")
            rss.write(f"      <link>{project_root}/blob/master/{path_out}</link>\n")
            rss.write(f"      <guid>{project_root}/blob/master/{path_out}</guid>\n")
            rss.write(f"      <pubDate>{pub_date}</pubDate>\n")
            rss.write("    </item>\n")
        rss.write("  </channel>\n")
        rss.write("</rss>\n")


if __name__ == '__main__':
    app()
