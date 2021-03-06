'''
train
'''
import math
import os
import pickle
import random
from functools import partial

import time
import torch
from pandas import np
from tqdm import tqdm

from src import util, model, transformer, dataloader
from src.decoding import get_decode_fn, Decode
from src.model import dummy_mask
from src.trainer import BaseTrainer

tqdm.monitor_interval = 0

tqdm = partial(tqdm, bar_format='{l_bar}{r_bar}')


class Data(util.NamedEnum):
    g2p = 'g2p'
    p2g = 'p2g'
    news15 = 'news15'
    histnorm = 'histnorm'
    sigmorphon16task1 = 'sigmorphon16task1'
    sigmorphon17task1 = 'sigmorphon17task1'
    sigmorphon19task1 = 'sigmorphon19task1'
    sigmorphon19task2 = 'sigmorphon19task2'
    lemma = 'lemma'
    lemmanotag = 'lemmanotag'
    lematus = 'lematus'
    unimorph = 'unimorph'


class Arch(util.NamedEnum):
    soft = 'soft'  # soft attention without input-feeding
    hard = 'hard'  # hard attention with dynamic programming without input-feeding
    approxihard = 'approxihard'  # hard attention with REINFORCE approximation without input-feeding
    softinputfeed = 'softinputfeed'  # soft attention with input-feeding
    largesoftinputfeed = 'largesoftinputfeed'  # soft attention with uncontrolled input-feeding
    approxihardinputfeed = 'approxihardinputfeed'  # hard attention with REINFORCE approximation with input-feeding
    hardmono = 'hardmono'  # hard monotonic attention
    hmm = 'hmm'  # 0th-order hard attention without input-feeding
    hmmfull = 'hmmfull'  # 1st-order hard attention without input-feeding
    transformer = 'transformer'
    universaltransformer = 'universaltransformer'
    tagtransformer = 'tagtransformer'
    taguniversaltransformer = 'taguniversaltransformer'


class Trainer(BaseTrainer):
    '''docstring for Trainer.'''
    def set_args(self):
        '''
        get_args
        '''
        # yapf: disable
        super().set_args()
        parser = self.parser
        parser.add_argument('--dataset', required=True, type=Data, choices=list(Data))
        parser.add_argument('--max_seq_len', default=128, type=int)
        parser.add_argument('--max_decode_len', default=128, type=int)
        parser.add_argument('--init', default='', help='control initialization')
        parser.add_argument('--dropout', default=0.2, type=float, help='dropout prob', nargs='+')
        parser.add_argument('--embed_dim', default=100, type=int, help='embedding dimension')
        parser.add_argument('--nb_heads', default=4, type=int, help='number of attention head', nargs='+')
        parser.add_argument('--src_layer', default=1, type=int, help='source encoder number of layers', nargs='+')
        parser.add_argument('--trg_layer', default=1, type=int, help='target decoder number of layers', nargs='+')
        parser.add_argument('--src_hs', default=200, type=int, help='source encoder hidden dimension')
        parser.add_argument('--trg_hs', default=200, type=int, help='target decoder hidden dimension')
        parser.add_argument('--label_smooth', default=0., type=float, help='label smoothing coeff')
        parser.add_argument('--tie_trg_embed', default=False, action='store_true', help='tie decoder input & output embeddings')
        parser.add_argument('--arch', required=True, type=Arch, choices=list(Arch))
        parser.add_argument('--nb_sample', default=2, type=int, help='number of sample in REINFORCE approximation')
        parser.add_argument('--wid_siz', default=11, type=int, help='maximum transition in 1st-order hard attention')
        parser.add_argument('--indtag', default=False, action='store_true', help='separate tag from source string')
        parser.add_argument('--decode', default=Decode.greedy, type=Decode, choices=list(Decode))
        parser.add_argument('--mono', default=False, action='store_true', help='enforce monotonicity')
        parser.add_argument('--bestacc', default=False, action='store_true', help='select model by accuracy only')
        parser.add_argument('--use_copy', help="bool flag to use copy mechanism")
        parser.add_argument('--align', default=None, type=str, help='path to alignment map')
        parser.add_argument('--no_estop', default=False, action='store_true', help='no early stopping')
        parser.add_argument('--no_scale', default=False, action='store_true', help='no embed scaling')
        parser.add_argument('--sample', default=False, action='store_true',
                            help='tie decoder input & output embeddings')
        # yapf: enable

    def load_data(self, dataset, train, dev, test):
        assert self.data is None
        logger = self.logger
        params = self.params
        # yapf: disable
        if params.arch == Arch.hardmono:
            if dataset == Data.sigmorphon17task1:
                self.data = dataloader.AlignSIGMORPHON2017Task1(train, dev, test, params.shuffle)
            elif dataset == Data.g2p:
                self.data = dataloader.AlignStandardG2P(train, dev, test, params.shuffle)
            elif dataset == Data.news15:
                self.data = dataloader.AlignTransliteration(train, dev, test, params.shuffle)
            else:
                raise ValueError
        else:
            if dataset == Data.sigmorphon17task1:
                if params.indtag:
                    self.data = dataloader.TagSIGMORPHON2017Task1(train, dev, test, params.shuffle)
                else:
                    self.data = dataloader.SIGMORPHON2017Task1(train, dev, test, params.shuffle)
            elif dataset == Data.unimorph:
                if params.indtag:
                    self.data = dataloader.TagUnimorph(train, dev, test, params.shuffle)
                else:
                    self.data = dataloader.Unimorph(train, dev, test, params.shuffle)
            elif dataset == Data.sigmorphon19task1:
                assert isinstance(train, list) and len(train) == 2 and params.indtag
                self.data = dataloader.TagSIGMORPHON2019Task1(train, dev, test, params.shuffle)
            elif dataset == Data.sigmorphon19task2:
                assert params.indtag
                self.data = dataloader.TagSIGMORPHON2019Task2(train, dev, test, params.shuffle)
            elif dataset == Data.g2p:
                self.data = dataloader.StandardG2P(train, dev, test, params.shuffle)
            elif dataset == Data.p2g:
                self.data = dataloader.StandardP2G(train, dev, test, params.shuffle)
            elif dataset == Data.news15:
                self.data = dataloader.Transliteration(train, dev, test, params.shuffle)
            elif dataset == Data.histnorm:
                self.data = dataloader.Histnorm(train, dev, test, params.shuffle)
            elif dataset == Data.sigmorphon16task1:
                if params.indtag:
                    self.data = dataloader.TagSIGMORPHON2016Task1(train, dev, test, params.shuffle)
                else:
                    self.data = dataloader.SIGMORPHON2016Task1(train, dev, test, params.shuffle)
            elif dataset == Data.lemma:
                if params.indtag:
                    self.data = dataloader.TagLemmatization(train, dev, test, params.shuffle)
                else:
                    self.data = dataloader.Lemmatization(train, dev, test, params.shuffle)
            elif dataset == Data.lemmanotag:
                self.data = dataloader.LemmatizationNotag(train, dev, test, params.shuffle)
            else:
                raise ValueError
        # yapf: enable
        logger.info('src vocab size %d', self.data.source_vocab_size)
        logger.info('trg vocab size %d', self.data.target_vocab_size)
        logger.info('src vocab %r', self.data.source[:500])
        logger.info('trg vocab %r', self.data.target[:500])

    def build_model(self):
        assert self.model is None
        params = self.params
        if params.arch == Arch.hardmono:
            params.indtag, params.mono = True, True
        kwargs = dict()
        kwargs['src_vocab_size'] = self.data.source_vocab_size
        kwargs['trg_vocab_size'] = self.data.target_vocab_size
        kwargs['embed_dim'] = params.embed_dim

        kwargs['nb_heads'] = params.nb_heads

        kwargs['dropout_p'] = params.dropout

        kwargs['tie_trg_embed'] = params.tie_trg_embed
        kwargs['src_hid_size'] = params.src_hs
        kwargs['trg_hid_size'] = params.trg_hs

        kwargs['src_nb_layers'] = params.src_layer

        kwargs['trg_nb_layers'] = params.trg_layer

        kwargs['nb_attr'] = self.data.nb_attr
        kwargs['nb_sample'] = params.nb_sample
        kwargs['wid_siz'] = params.wid_siz
        kwargs['label_smooth'] = params.label_smooth
        kwargs['src_c2i'] = self.data.source_c2i
        kwargs['trg_c2i'] = self.data.target_c2i
        kwargs['attr_c2i'] = self.data.attr_c2i
        kwargs['use_copy'] = params.use_copy
        kwargs['align'] = params.align
        kwargs['no_estop'] = params.no_estop
        kwargs['no_scale'] = params.no_scale

        model_class = None
        indtag, mono = True, True
        # yapf: disable
        fancy_classfactory = {
            (Arch.hardmono, indtag, mono): model.HardMonoTransducer,
            (Arch.soft, indtag, not mono): model.TagTransducer,
            (Arch.hard, indtag, not mono): model.TagHardAttnTransducer,
            (Arch.hmm, indtag, not mono): model.TagHMMTransducer,
            (Arch.hmm, indtag, mono): model.MonoTagHMMTransducer,
            (Arch.hmmfull, indtag, not mono): model.TagFullHMMTransducer,
            (Arch.hmmfull, indtag, mono): model.MonoTagFullHMMTransducer,
        }
        regular_classfactory = {
            Arch.soft: model.Transducer,
            Arch.hard: model.HardAttnTransducer,
            Arch.softinputfeed: model.InputFeedTransducer,
            Arch.largesoftinputfeed: model.LargeInputFeedTransducer,
            Arch.approxihard: model.ApproxiHardTransducer,
            Arch.approxihardinputfeed: model.ApproxiHardInputFeedTransducer,
            Arch.hmm: model.HMMTransducer,
            Arch.hmmfull: model.FullHMMTransducer,
            Arch.transformer: transformer.Transformer,
            Arch.universaltransformer: transformer.UniversalTransformer,
            Arch.tagtransformer: transformer.TagTransformer,
            Arch.taguniversaltransformer: transformer.TagUniversalTransformer,
        }
        # yapf: enable
        if params.indtag or params.mono:
            model_class = fancy_classfactory[(params.arch, params.indtag,
                                              params.mono)]
        else:
            model_class = regular_classfactory[params.arch]
        self.model = model_class(**kwargs)
        if params.indtag:
            self.logger.info('number of attribute %d', self.model.nb_attr)
            self.logger.info('dec 1st rnn %r', self.model.dec_rnn.layers[0])
        if params.arch in [
                Arch.softinputfeed, Arch.approxihardinputfeed,
                Arch.largesoftinputfeed
        ]:
            self.logger.info('merge_input with %r', self.model.merge_input)
        self.logger.info('model: %r', self.model)
        self.logger.info('number of parameter %d',
                         self.model.count_nb_params())
        self.model = self.model.to(self.device)

    def dump_state_dict(self, filepath):
        util.maybe_mkdir(filepath)
        self.model = self.model.to('cpu')
        t.save(self.model.state_dict(), filepath)
        self.model = self.model.to(self.device)
        self.logger.info(f'dump to {filepath}')

    def load_state_dict(self, filepath):
        state_dict = t.load(filepath)
        self.model.load_state_dict(state_dict)
        self.model = self.model.to(self.device)
        self.logger.info(f'load from {filepath}')

    def setup_evalutator(self):
        arch, dataset = self.params.arch, self.params.dataset
        if arch == Arch.hardmono:
            if dataset == Data.news15:
                self.evaluator = util.PairTranslitEvaluator()
            elif dataset == Data.sigmorphon17task1:
                self.evaluator = util.PairBasicEvaluator()
            elif dataset == Data.g2p:
                self.evaluator = util.PairG2PEvaluator()
            else:
                raise ValueError
        else:
            if dataset == Data.news15:
                self.evaluator = util.TranslitEvaluator()
            elif dataset == Data.g2p:
                self.evaluator = util.G2PEvaluator()
            elif dataset == Data.p2g:
                self.evaluator = util.P2GEvaluator()
            elif dataset == Data.histnorm:
                self.evaluator = util.HistnormEvaluator()
            else:
                self.evaluator = util.BasicEvaluator()

    def evaluate(self, mode, epoch_idx, decode_fn, batch_size):
        self.model.eval()
        if True or batch_size == 1:
        # if batch_size == 1:
                sampler, nb_instance = self.iterate_instance(mode)  #this
        else:
            sampler, nb_instance = self.iterate_batch(mode, batch_size)  # this
        decode_fn.reset()

        results = self.evaluator.evaluate_all(sampler, nb_instance, self.model,
                                              decode_fn)
        decode_fn.reset()
        for result in results:
            self.logger.info(
                f'{mode} {result.long_desc} is {result.res} at epoch {epoch_idx}'
            )
        return results

    def decode(self, mode, write_fp, decode_fn):
        self.model.eval()
        cnt = 0
        sampler, nb_instance = self.iterate_instance(mode)
        decode_fn.reset()

        outputs = []
        for src, trg in tqdm(sampler(), total=nb_instance):
            pred, gen_prob_vals, _ = decode_fn(self.model, src)
            if gen_prob_vals:
                p_gen, copy_prob, gen_prob = gen_prob_vals
            else:
                p_gen, copy_prob, gen_prob = None, None, None
            # p_gen = gen_prob_vals
            dist = util.edit_distance(pred, trg.view(-1).tolist()[1:-1])

            src_mask = dummy_mask(src)
            trg_mask = dummy_mask(trg)
            data = (src, src_mask, trg, trg_mask)
            loss = self.model.get_loss(data).item()
            src = self.data.decode_source(src)
            trg = self.data.decode_target(trg)[1:-1]
            pred = self.data.decode_target(pred)
            outputs.append([pred, trg, loss, dist, src, p_gen, copy_prob, gen_prob])

        with open(f'{write_fp}.{mode}.tsv', 'w', encoding='utf-8') as fp:
            fp.write(f'prediction\ttarget\tloss\tdist\n')
            for pred, trg, loss, dist, _, _, _, _ in outputs:
                fp.write(
                    f'{" ".join(pred)}\t{" ".join(trg)}\t{loss}\t{dist}\n')
                cnt += 1

        with open(f'{write_fp}.{mode}_gh.tsv', 'w', encoding='utf-8') as fp:
            fp.write(f'target\tprediction\n')
            for pred, trg, _, _, _, _, _, _ in outputs:
                fp.write(
                    f'{" ".join(trg)}\t{" ".join(pred)}\n')
                cnt += 1

        with open(f'{write_fp}.{mode}_src_pred.tsv', 'w', encoding='utf-8') as fp:
            for pred, trg, _, _, src, _, _, _ in outputs:
                fp.write(
                    f'{"".join(src[1:-1])}\t{" ".join(pred)}\n')
                cnt += 1

        with open(f'{write_fp}.{mode}_copy-probs.tsv', 'w', encoding='utf-8') as fp:
            fp.write(f'source\ttarget\tprediction\tdist\n')
            for pred, trg, _, _, src, p_gen, copy_prob, gen_prob in outputs:
                fp.write(
                    f'{" ".join(src)}\t{" ".join(trg)}\t{" ".join(pred)}\n')
                fp.write(f'p_gen')
                fp.write(f'{p_gen}\n')
                fp.write(f'copy_prob')
                fp.write(f'{copy_prob}\n')
                fp.write(f'gen_prob')
                fp.write(f'{gen_prob}\n')

                cnt += 1

        decode_fn.reset()
        self.logger.info(f'finished decoding {cnt} {mode} instance')

    def select_model(self):
        best_res = [m for m in self.models if m.evaluation_result][0]
        best_acc = [m for m in self.models if m.evaluation_result][0]
        best_devloss = self.models[0]
        for model in self.models:
            if not model.evaluation_result:
                continue
            if type(self.evaluator) == util.BasicEvaluator or \
               type(self.evaluator) == util.G2PEvaluator or \
               type(self.evaluator) == util.P2GEvaluator or \
               type(self.evaluator) == util.HistnormEvaluator:
                # [acc, edit distance / per ]
                # if model.evaluation_result[0].res >= best_res.evaluation_result[0].res and \
                #    model.evaluation_result[1].res <= best_res.evaluation_result[1].res:
                if model.evaluation_result[0].res >= best_res.evaluation_result[0].res:
                    best_res = model
            elif type(self.evaluator) == util.TranslitEvaluator:
                if model.evaluation_result[0].res >= best_res.evaluation_result[0].res and \
                   model.evaluation_result[1].res >= best_res.evaluation_result[1].res:
                    best_res = model
            else:
                raise NotImplementedError
            if model.evaluation_result[0].res >= best_acc.evaluation_result[0].res:
                best_acc = model
            if model.devloss <= best_devloss.devloss:
                best_devloss = model
        if self.params.bestacc:
            best_fp = best_acc.filepath
        else:
            best_fp = best_res.filepath
        return best_fp, set([best_fp])


def main():
    '''
    main
    '''
    trainer = Trainer()
    params = trainer.params
    decode_fn = get_decode_fn(params.decode, params.max_decode_len)
    trainer.load_data(params.dataset, params.train, params.dev, params.test)
    trainer.setup_evalutator()
    if params.load and params.load != '0':
        if params.load == 'smart':
            start_epoch = trainer.smart_load_model(params.model) + 1
        else:
            start_epoch = trainer.load_model(params.load) + 1
        trainer.logger.info('continue training from epoch %d', start_epoch)
        trainer.setup_training()
        trainer.load_training(params.model)
    else:  # start from scratch
        start_epoch = 0
        trainer.build_model()
        if params.init:
            if os.path.isfile(params.init):
                trainer.load_state_dict(params.init)
            else:
                trainer.dump_state_dict(params.init)
        trainer.setup_training()

    trainer.run(start_epoch, decode_fn=decode_fn)


if __name__ == '__main__':
    main()
