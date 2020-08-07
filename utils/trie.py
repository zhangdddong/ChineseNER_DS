#!/usr/bin/python3
# -*- coding: UTF-8 -*-
# __author__ = 'zd'

import collections


class TrieNode(object):
    def __init__(self):
        self.children = collections.defaultdict(TrieNode)
        self.is_word = False


class Trie(object):
    def __init__(self):
        self.root = TrieNode()

    def insert(self, word):
        current = self.root
        for letter in word:
            current = current.children[letter]
        current.is_word = True

    def search(self, word):
        current = self.root
        for letter in word:
            current = current.children.get(letter)
            if current is None:
                return False
        return current.is_word

    def starts_with(self, prefix):
        current = self.root
        for letter in prefix:
            current = current.children.get(letter)
            if current is None:
                return False
        return True

    def enumerate_match(self, word, space='_', backward=False):
        matched = []
        while len(word) > 1:
            if self.search(word):
                matched.append(space.join(word[:]))
            del word[-1]
        return matched
