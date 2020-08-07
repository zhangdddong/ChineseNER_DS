# ChineseNER_DS
Leveraging Lexical Features for Chinese Named Entity Recognition via Static and Dynamic Weighting

### Requirement:

~~~shell
python: 3.6.0
tensorflow: 1.4.0
~~~

### Input format:

~~~shell
美	B-LOC
国	E-LOC
的	O
华	B-PER
莱	I-PER
士	E-PER

我	O
跟	O
他	O
谈	O
笑	O
风	O
生	O 
~~~

### Pretrained Embeddings:

Character embeddings (gigaword_chn.all.a2b.uni.ite50.vec): and  Word(Lattice) embeddings (sgns.merge.word):  [Baidu Pan](https://pan.baidu.com/s/1h1G4eow5nzwUHbu1eJKNzg) 提取码：w0au

#### How to run the code?

1. Download the character embeddings and word embeddings and put them in the `data` folder.
2. run`python main.py`

### Cite: 

Leveraging Lexical Features for Chinese Named Entity Recognition via Static and Dynamic Weighting

