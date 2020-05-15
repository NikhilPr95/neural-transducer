import os

import fire

LANGS = {
    'austronesian': 'mlg ceb hil tgl mao'.split(),
    'germanic': 'dan isl nob swe nld eng deu gmh frr ang'.split(),
    'niger-congo': 'nya kon lin lug sot swa zul aka gaa'.split(),
    'oto-manguean': 'cpa azg xty zpv ctp czn cly otm ote pei'.split(),
    'uralic': 'est fin izh krl liv vep vot mhr myv mdf sme'.split()
}

MAX_HALL = 10_000
IN_DIR = 'task0-data'
OUT_DIR = 'task0-data/out'


def read_file(file):
    with open(file) as fp:
        for line in fp:
            line = line.strip()
            if not line:
                continue
            toks = line.split('\t')
            if len(toks) == 3:
                yield toks


def regular(family):
    for lang in sorted(LANGS[family]):
        for mode in ['trn', 'dev']:
            with open(f'{OUT_DIR}/{lang}.{mode}', 'w') as fp:
                for toks in read_file(f'{IN_DIR}/{family}/{lang}.{mode}'):
                    print(*toks, sep='\t', file=fp)


def halluication(family):
    for lang in sorted(LANGS[family]):
        mode = 'trn'
        if not os.path.isfile(f'{IN_DIR}/{family}/{lang}.hall'):
            print('missing .hall for', lang)
            continue
        with open(f'{OUT_DIR}/{lang}.hall.{mode}', 'w') as fp:
            for toks in read_file(f'{IN_DIR}/{family}/{lang}.{mode}'):
                print(*toks, sep='\t', file=fp)
            for i, toks in enumerate(
                    read_file(f'{IN_DIR}/{family}/{lang}.hall')):
                if i == MAX_HALL:
                    break
                print(toks[0], toks[1], f'fake;{toks[2]}', sep='\t', file=fp)


def concat_langid(family):
    for mode in ['trn', 'dev']:
        with open(f'{OUT_DIR}/{family}.{mode}', 'w') as fp:
            for lang in sorted(LANGS[family]):
                for toks in read_file(f'{IN_DIR}/{family}/{lang}.{mode}'):
                    print(toks[0],
                          toks[1],
                          f'{lang};{toks[2]}',
                          sep='\t',
                          file=fp)


def concat_halluication(family):
    mode = 'trn'
    for lang in sorted(LANGS[family]):
        if not os.path.isfile(f'{IN_DIR}/{family}/{lang}.hall'):
            print('missing .hall for', lang)
            return
    with open(f'{OUT_DIR}/{family}.hall.{mode}', 'w') as fp:
        for lang in sorted(LANGS[family]):
            for toks in read_file(f'{IN_DIR}/{family}/{lang}.{mode}'):
                print(toks[0], toks[1], f'{lang};{toks[2]}', sep='\t', file=fp)
            for i, toks in enumerate(
                    read_file(f'{IN_DIR}/{family}/{lang}.hall')):
                if i == MAX_HALL:
                    break
                print(toks[0],
                      toks[1],
                      f'fake;{lang};{toks[2]}',
                      sep='\t',
                      file=fp)


class Main:
    def regular(self):
        for family in LANGS.keys():
            print('regular', family)
            regular(family)

    def hall(self):
        for family in LANGS.keys():
            print('hall', family)
            halluication(family)

    def concat(self):
        for family in LANGS.keys():
            print('concat', family)
            concat_langid(family)

    def concat_hall(self):
        for family in LANGS.keys():
            print('concat_hall', family)
            concat_halluication(family)

    def all(self):
        self.regular()
        self.hall()
        self.concat()
        self.concat_hall()

    def gen_langs(self):
        langs = []
        for family in LANGS.keys():
            langs.extend(LANGS[family])
        print(' '.join(sorted(langs)))
        print(len(langs))

    def gen_family(self):
        family = list(LANGS.keys())
        print(' '.join(sorted(family)))
        print(len(family))


if __name__ == "__main__":
    try:
        os.mkdir(OUT_DIR)
    except:
        pass
    fire.Fire(Main)
