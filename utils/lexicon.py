#!/usr/bin/python3
# -*- coding: UTF-8 -*-
# __author__ = 'zd'

from utils.trie import Trie


class Lexicon(object):
    def __init__(self, lower=True):
        self.lower = lower

        self.trie = Trie()
        self.ent2type = {}            # word list to type
        self.ent2id = {'<UNK>': 0}    # word list to id
        self.space = ''

    def enumerate_match_list(self, word_list):
        if self.lower:
            word_list = [word.lower() for word in word_list]
        match_list = self.trie.enumerate_match(word_list, self.space)
        return match_list

    def insert(self, word_list, source):
        if self.lower:
            word_list = [word.lower() for word in word_list]
        self.trie.insert(word_list)
        string = self.space.join(word_list)
        if string not in self.ent2type:
            self.ent2type[string] = source
        if string not in self.ent2id:
            self.ent2id[string] = len(self.ent2id)

    def search_id(self, word_list):
        if self.lower:
            word_list = [word.lower() for word in word_list]
        string = self.space.join(word_list)
        if string in self.ent2id:
            return self.ent2id[string]
        return self.ent2id['<UNK>']

    def search_type(self, word_list):
        if self.lower:
            word_list = [word.lower() for word in word_list]
        string = self.space.join(word_list)
        if string in self.ent2type:
            return self.ent2type[string]
        print('Error in finding entity type at lexicon.py, exit programming')
        exit(0)

    def size(self):
        return len(self.ent2type)

    def clean(self):
        self.trie = Trie()
        self.ent2type = {}
        self.ent2id = {}
        self.space = ''
