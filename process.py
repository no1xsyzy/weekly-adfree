import json
import math
import sys
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
        guess = nb.check_spam(cut)
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


@app.command()
def proc_all():
    load_nb()

    outdir = Path('docs')

    outdir.mkdir(exist_ok=True)

    for p in all_doc_paths():
        doc = load_doc(p)
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

        (outdir/p.name).write_text(result, encoding='utf-8')


if __name__ == '__main__':
    app()
