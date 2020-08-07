#!/usr/bin/python3
# -*- coding: UTF-8 -*-
__author__ = 'zd'

import tensorflow as tf
from tensorflow.contrib.layers.python.layers import initializers
import tensorflow.contrib.rnn as rnn
from tensorflow.contrib.crf import crf_log_likelihood
import numpy as np
from tensorflow.contrib.crf import viterbi_decode
import data_utils


class Model(object):
    def __init__(self, config):
        self.config = config
        self.lr = config['lr']
        self.word_dim = config['word_dim']
        self.lstm_dim = config['lstm_dim']
        self.seg_dim = config['seg_dim']
        self.num_tags = config['num_tags']
        self.num_words = config['num_words']
        self.num_segs = 4

        # lexicon
        self.num_lexicon = config['num_lexicon']
        self.lexicon_dim = 300

        self.global_step = tf.Variable(0, trainable=False)
        self.best_dev_f1 = tf.Variable(0.0, trainable=False)
        self.best_test_f1 = tf.Variable(0.0, trainable=False)
        self.initializer = initializers.xavier_initializer()

        # 申请占位符
        self.word_inputs = tf.placeholder(dtype=tf.int32, shape=[None, None], name='wordInputs')
        self.seg_inputs = tf.placeholder(dtype=tf.int32, shape=[None, None], name='segInputs')
        self.lexicon_inputs = tf.placeholder(dtype=tf.int32, shape=[None, None], name='lexiconInputs')
        self.targets = tf.placeholder(dtype=tf.int32, shape=[None, None], name='targets')
        self.dropout = tf.placeholder(dtype=tf.float32, name='dropout')

        used = tf.sign(tf.abs(self.word_inputs))
        length = tf.reduce_sum(used, reduction_indices=1)
        self.lengths = tf.cast(length, tf.int32)
        self.batch_size = tf.shape(self.word_inputs)[0]
        self.sentence_length = tf.shape(self.word_inputs)[-1]

        # embedding层单词和分词信息
        embedding = self.embedding_layer(self.word_inputs, self.seg_inputs, self.lexicon_inputs, config)

        # bilstm输入层
        lstm_inputs = tf.nn.dropout(embedding, self.dropout)

        # bilstm输出层
        lstm_outputs = self.biLSTM_layer(lstm_inputs, self.lstm_dim, self.lengths)

        # 投影层
        self.logits = self.project_layer(lstm_outputs)

        # 损失层
        self.loss = self.crf_loss_layer(self.logits, self.lengths)

        with tf.variable_scope('optimizer'):
            optimizer = self.config['optimizer']
            if optimizer == 'sgd':
                self.opt = tf.train.GradientDescentOptimizer(self.lr)
            elif optimizer == 'adam':
                self.opt = tf.train.AdamOptimizer(self.lr)
            elif optimizer == 'adgrad':
                self.opt = tf.train.AdagradDAOptimizer(self.lr)
            else:
                raise Exception('优化器错误')
            grad_vars = self.opt.compute_gradients(self.loss)
            capped_grad_vars = [[tf.clip_by_value(g, -self.config['clip'], self.config['clip']),v] for g, v in grad_vars]
            self.train_op = self.opt.apply_gradients(capped_grad_vars, self.global_step)

            # 保存模型
            self.saver = tf.train.Saver(tf.global_variables(), max_to_keep=5)

    def embedding_layer(self, word_inputs, seg_inputs, lexicon_inputs, config, name=None):
        """
        :param word_inputs: [batch_size, sentence_length] one-hot encoding
        :param seg_inputs: segment information
        :param lexicon_inputs: lexicon information
        :param config: config
        :param name: the name of layers
        :return: [batch_size, sentence_length, word_embedding + seg_embedding]
        """
        embedding = []
        with tf.variable_scope('word_embedding' if not name else name):
            self.word_lookup = tf.get_variable(
                name='word_embedding',
                shape=[self.num_words, self.word_dim],
                initializer=self.initializer
            )
            embedding.append(tf.nn.embedding_lookup(self.word_lookup, word_inputs))

            if config['lexicon']:
                with tf.variable_scope('lexicon_embedding'):
                    self.lexicon_lookup = tf.get_variable(
                        name='lexicon_embedding',
                        shape=[self.num_lexicon, self.lexicon_dim],
                        initializer=self.initializer
                    )
                    lexicon_features = tf.nn.embedding_lookup(self.lexicon_lookup, lexicon_inputs)
                    self.gaz_length = tf.shape(lexicon_features)[1]
                    # statical information
                    prob = tf.fill(dims=tf.shape(lexicon_features), value=1.0 / tf.cast(self.gaz_length, tf.float32))
                    s_info = tf.math.multiply(lexicon_features, prob)
                    s_info = tf.reduce_sum(s_info, axis=1)
                    s_info = tf.expand_dims(s_info, axis=1)
                    s_info = tf.tile(s_info, multiples=[1, self.sentence_length, 1])
                    embedding.append(s_info)
                    # dynamic information
                    with tf.variable_scope('attention_layer'):
                        context_vector, _ = self.attention_layer(lexicon_features)
                        context_vector = tf.expand_dims(context_vector, axis=1)
                        context_vector = tf.tile(context_vector, multiples=[1, self.sentence_length, 1])
                        embedding.append(context_vector)

            if config['seg_dim']:
                with tf.variable_scope('seg_embedding'):
                    self.seg_lookup = tf.get_variable(
                        name='seg_embedding',
                        shape=[self.num_segs, self.seg_dim],
                        initializer=self.initializer
                    )
                    embedding.append(tf.nn.embedding_lookup(self.seg_lookup, seg_inputs))
        return tf.concat(embedding, axis=-1)

    def biLSTM_layer(self, lstm_inputs, lstm_dim, lengths, name=None):
        """
        :param lstm_inputs: [batch_size, sentences_length, emd_size]
        :param lstm_dim:
        :param lengths:
        :param name:
        :return: [batch_size, sentence_length, 2 * lstm_dim]
        """
        with tf.variable_scope('word_biLSTM' if not name else name):
            lstm_cell = {}
            for direction in ['forward', 'backward']:
                with tf.variable_scope(direction):
                    lstm_cell[direction] = rnn.CoupledInputForgetGateLSTMCell(
                        lstm_dim,
                        use_peepholes=True,
                        initializer=self.initializer,
                        state_is_tuple=True
                    )
            outputs, final_status = tf.nn.bidirectional_dynamic_rnn(
                lstm_cell['forward'],
                lstm_cell['backward'],
                lstm_inputs,
                dtype=tf.float32,
                sequence_length=lengths
            )
        return tf.concat(outputs, axis=2)

    def project_layer(self, lstm_outputs, name=None):
        """
        :param lstm_outputs: [batch_size, sentence_length, 2 * lstm_dim]
        :param name:
        :return: [batch_size, sentence_length, num_tags]
        """
        with tf.variable_scope('project_layer' if not name else name):
            with tf.variable_scope('hidden_layer'):
                W = tf.get_variable(
                    'W',
                    shape=[self.lstm_dim * 2, self.lstm_dim],
                    dtype=tf.float32,
                    initializer=self.initializer
                )
                b = tf.get_variable(
                    'b',
                    shape=[self.lstm_dim],
                    dtype=tf.float32,
                    initializer=tf.zeros_initializer()
                )
                out_put = tf.reshape(lstm_outputs, shape=[-1, 2 * self.lstm_dim])
                hidden = tf.tanh(tf.nn.xw_plus_b(out_put, W, b))
            with tf.variable_scope('logits'):
                W = tf.get_variable(
                    'W',
                    shape=[self.lstm_dim, self.num_tags],
                    dtype=tf.float32,
                    initializer=self.initializer
                )
                b = tf.get_variable(
                    'b',
                    shape=[self.num_tags],
                    dtype=tf.float32,
                    initializer=tf.zeros_initializer()
                )
                pred = tf.nn.xw_plus_b(hidden, W, b)
        return tf.reshape(pred, [-1, self.sentence_length, self.num_tags])

    def crf_loss_layer(self, project_logits, lengths, name=None):
        """
        :param project_logits: [batch_size, sentenes_length, num_tags]
        :param lengths: [...]
        :param name:
        :return: scalar loss
        """
        with tf.variable_scope('crf_loss' if not name else name):
            small_value = -10000.0
            start_logits = tf.concat(
                [
                    small_value * tf.ones(shape=[self.batch_size, 1, self.num_tags]),
                    tf.zeros(shape=[self.batch_size, 1, 1])
                ], axis=-1
            )
            pad_logits = tf.cast(
                small_value * tf.ones(shape=[self.batch_size, self.sentence_length, 1]),
                dtype=tf.float32
            )
            logits = tf.concat([project_logits, pad_logits], axis=-1)
            logits = tf.concat([start_logits, logits], axis=1)
            targets = tf.concat(
                [
                    tf.cast(self.num_tags * tf.ones([self.batch_size, 1]), tf.int32),
                    self.targets
                ], axis=-1
            )
            self.trans = tf.get_variable(
                'transitions',
                shape=[self.num_tags + 1, self.num_tags + 1],
                initializer=self.initializer
            )
            log_likelihood, self.trans =  crf_log_likelihood(
                inputs=logits,
                tag_indices=targets,
                transition_params=self.trans,
                sequence_lengths=lengths + 1
            )
        return tf.reduce_mean(-log_likelihood)

    def attention_layer(self, inputs):
        # Trainable parameters
        hidden_size = inputs.shape[2].value
        u_omega = tf.get_variable("u_omega", [hidden_size], initializer=tf.keras.initializers.glorot_normal())

        with tf.name_scope('v'):
            v = tf.tanh(inputs)

        # For each of the timestamps its vector of size A from `v` is reduced with `u` vector
        vu = tf.tensordot(v, u_omega, axes=1, name='vu')  # (B,T) shape
        alphas = tf.nn.softmax(vu, name='alphas')  # (B,T) shape

        # Output of (Bi-)RNN is reduced with attention vector; the result has (B,D) shape
        output = tf.reduce_sum(inputs * tf.expand_dims(alphas, -1), 1)

        # Final output with tanh
        output = tf.tanh(output)

        return output, alphas

    def decode(self, logits, lengths, matrix):
        """
        :param logits: [batch_size, sentences_length, num_tags]
        :param lengths:
        :param matrix:
        :return:
        """
        paths = []
        small = -1000.0
        start = np.asarray([[small] * self.num_tags + [0]])
        for score, length in zip(logits, lengths):
            score = score[:length]
            pad = small * np.ones([length, 1])
            logits = np.concatenate([score, pad], axis=1)
            logits = np.concatenate([start, logits], axis=0)
            path, _ = viterbi_decode(logits, matrix)

            paths.append(path[1:])
        return paths

    def create_feed_dict(self, is_train, batch):
        """
        :param is_train:
        :param batch:
        :return:
        """
        _, words, segs, tags, lexicon = batch
        feed_dict = {
            self.word_inputs: np.asarray(words),
            self.seg_inputs: np.asarray(segs),
            self.lexicon_inputs: np.asarray(lexicon),
            self.dropout: 1.0
        }
        if is_train:
            feed_dict[self.targets] = np.asarray(tags)
            feed_dict[self.dropout] = self.config['dropout_keep']
        return feed_dict

    def run_step(self, sess, is_train, batch):
        """
        :param sess:
        :param is_train:
        :param batch:
        :return:
        """
        feed_dict = self.create_feed_dict(is_train, batch)
        if is_train:
            global_step, loss, _ = sess.run(
                [self.global_step, self.loss, self.train_op], feed_dict
            )
            return global_step, loss
        else:
            lengths, logits = sess.run([self.lengths, self.logits], feed_dict)
            return lengths, logits

    def evaluate(self, sess, data_manager, id_to_tag):
        """
        :param sess:
        :param data_manager:
        :param id_to_tag:
        :return:
        """
        results = []
        trans = self.trans.eval()
        for batch in data_manager.iter_batch():
            strings = batch[0]
            tags = batch[-2]
            lengths, logits = self.run_step(sess, False, batch)
            batch_paths = self.decode(logits, lengths, trans)
            for i in range(len(strings)):
                result = []
                string = strings[i][:lengths[i]]
                gold = data_utils.bioes_to_bio([id_to_tag[int(x)] for x in tags[i][:lengths[i]]])
                pred = data_utils.bioes_to_bio([id_to_tag[int(x)] for x in batch_paths[i][:lengths[i]]])
                for char, gold, pred in zip(string, gold, pred):
                    result.append(" ".join([char, gold, pred]))
                results.append(result)
        return results
