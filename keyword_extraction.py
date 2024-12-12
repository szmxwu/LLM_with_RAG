

# -*- coding: utf-8 -*-'
#!/usr/bin/env python3

import pandas as pd
import numpy as np
import re
import time
from flashtext.keyword import KeywordProcessor  # 源码被修改过，文件为keyword.py
from datetime import datetime
import warnings
import configparser
from pprint import pprint
warnings.filterwarnings("ignore")


def timing_decorator(func):
    def wrapper(*args, **kwargs):
        start_time = time.time()
        result = func(*args, **kwargs)
        end_time = time.time()
        # print(f"Time spent on {func.__name__}: {end_time - start_time:.3f}s")
        return result
    return wrapper


def GetLevelDic(firstdf):  # 从excel部位字典中读取keyword
    partdic = {}
    i = 0
    axis_start = [0]*6
    axis_end = [0]*6
    hiatus = firstdf[(firstdf['起始坐标'] == np.nan) | (firstdf['终止坐标'] == np.nan)]
    if len(hiatus) > 0:
        print("axis loss:", hiatus)
    for index, row in firstdf.iterrows():
        Partlist = []
        parts = [[], [], [], [], [], []]
        if row["六级部位"] is not np.nan:
            parts[5] = row['六级部位'].split("|")
            Partlist.append(parts[5][0])
            axis_start[5] = row['起始坐标']
            axis_end[5] = row['终止坐标']
        if row["五级部位"] is not np.nan:
            parts[4] = row['五级部位'].split("|")
            Partlist.append(parts[4][0])
            temp = firstdf[firstdf['五级部位'] == row['五级部位']]
            axis_start[4] = temp['起始坐标'].min()
            axis_end[4] = temp['终止坐标'].max()
        if row["四级部位"] is not np.nan:
            parts[3] = row['四级部位'].split("|")
            Partlist.append(parts[3][0])
            temp = firstdf[firstdf['四级部位'] == row['四级部位']]
            axis_start[3] = temp['起始坐标'].min()
            axis_end[3] = temp['终止坐标'].max()
        if row["三级部位"] is not np.nan:
            parts[2] = row['三级部位'].split("|")
            Partlist.append(parts[2][0])
            temp = firstdf[firstdf['三级部位'] == row['三级部位']]
            axis_start[2] = temp['起始坐标'].min()
            axis_end[2] = temp['终止坐标'].max()
        if row["二级部位"] is not np.nan:
            parts[1] = row['二级部位'].split("|")
            Partlist.append(parts[1][0])
            temp = firstdf[firstdf['二级部位'] == row['二级部位']]
            axis_start[1] = temp['起始坐标'].min()
            axis_end[1] = temp['终止坐标'].max()
        if row["一级部位"] is not np.nan:
            parts[0] = row['一级部位'].split("|")
            Partlist.append(parts[0][0])
            axis_start[0] = firstdf['起始坐标'].min()
            axis_end[0] = firstdf['终止坐标'] .max()
        for i in range(6):
            newlist = Partlist[::-1]
            newlist = newlist[:i+1]
            if parts[i] != []:
                # print(newlist,axis_start,axis_end)
                newlist.append((axis_start[i], axis_end[i]))
                partdic[tuple(newlist)] = parts[i]
    # print(partdic)
    return partdic


# 读取.ini文件
conf = configparser.ConfigParser()
conf.read('system_config.ini',encoding='utf-8')
stop_pattern = conf.get("sentence", "stop_pattern")
sentence_pattern = conf.get("sentence", "sentence_pattern")
tipwords = conf.get("sentence", "tipwords")
punctuation = conf.get("clean", "punctuation")
ignore_keywords = conf.get("clean", "ignore_keywords")
Ignore_sentence = conf.get("clean", "Ignore_sentence")
stopwords = conf.get("clean", "stopwords")
second_root = conf.get("clean", "second_root")
absolute_norm = conf.get("positive", "absolute_norm")
absolute_illness = conf.get("positive", "absolute_illness").split("|")
NormKeyWords = conf.get("positive", "NormKeyWords")
illness_words = conf.get("positive", "illness_words")
sole_words = conf.get("positive", "sole_words")
deny_words = conf.get("positive", "deny_words")
spine_words = conf.get("clean", "spine")
dualparts=conf.get("orientation", "dualparts")
PATH_REPLACE_FILE = "documents/replace.xlsx"
PATH_HAND_DICT_FILE = "documents/hand_dict.xlsx"

# 部位知识图谱
bodypartsknowledgegraph = pd.read_excel(PATH_HAND_DICT_FILE, sheet_name=0)
knowledgegraph = []
firstlevel = set(bodypartsknowledgegraph["分类"].tolist())
for firtpart in firstlevel:
    temp = bodypartsknowledgegraph[bodypartsknowledgegraph["分类"] == firtpart]
    knowledgegraph.append(GetLevelDic(temp))

# 标题知识图谱
titlePartsKnowledgegraph = pd.read_excel(PATH_HAND_DICT_FILE, sheet_name=1)
title_knowledgegraph = []
title_firstlevel = set(titlePartsKnowledgegraph["分类"].tolist())
for title_firtpart in title_firstlevel:
    temp = titlePartsKnowledgegraph[titlePartsKnowledgegraph["分类"]
                                    == title_firtpart]
    title_knowledgegraph.append(GetLevelDic(temp))
# 报告词汇清洗
ReplaceTable = pd.read_excel(PATH_REPLACE_FILE, sheet_name=0).to_dict('records')
# 检查部位词汇清洗
PartReplaceTable = pd.read_excel(
    PATH_REPLACE_FILE, sheet_name=1).to_dict('records')
ConditionReplaceTable = pd.read_excel(
    PATH_REPLACE_FILE, sheet_name=2).to_dict('records')

#正常测量值
nomalMeasure = pd.read_excel(PATH_HAND_DICT_FILE, sheet_name=2)

#文本词还原
pattern1=re.compile(r'([^颈胸腰骶尾])(\d{1,2})[、|,|，|及|和](\d{1,2})([颈|胸|腰|骶|尾])(?!.*段)',flags=re.I)
pattern2=re.compile(r'([^颈胸腰骶尾/])(\d{1,2})[、|,|，|及|和]([颈|胸|腰|骶|尾])(\d{1,2})(?!.*段)' ,flags=re.I)
pattern3=re.compile(r'([^颈胸腰骶尾])(\d{1,2})(/\d{1,2})[、|,|，|及|和](\d{1,2})(/\d{1,2})([颈|胸|腰|骶|尾])' ,flags=re.I)
pattern4=re.compile(r'([^颈胸腰骶尾])(\d{1,2})(/\d{1,2})[、|,|，|及|和]([颈|胸|腰|骶|尾])(\d{1,2})(/\d{1,2})',flags=re.I) 
pattern5=re.compile(r'([腰|胸|颈|骶|尾|c|l|t|s])(\d{1,2})(/\d{1,2})?[、|,|，|及|和](\d{1,2})' ,flags=re.I)
pattern6=re.compile(r'([腰|胸|颈|骶|尾|c|l|t|s]\d{1,2})(/\d{1,2})?[,|，]([腰|胸|颈|骶|尾|c|l|t|s]\d{1,2})',flags=re.I) 
pattern7=re.compile(r"([胸|腰|颈|骶|c|t|l|s])(\d{1,2})/([胸|腰|颈|骶|c|t|l|s])?(\d{1,2})-([胸|腰|颈|骶|c|t|l|s])?(\d{1,2})/([胸|腰|颈|骶|c|t|l|s])?(\d{1,2})(?!.*段)",flags=re.I) 
pattern8=re.compile(r"([胸|腰|颈|骶|c|t|l|s])(\d{1,2})-([胸|腰|颈|骶|c|t|l|s])?(\d{1,2})(椎体)?(?!.*段)",flags=re.I) 
pattern9=re.compile(r'(^|[^a-zA-Z])C([1-8])(?!.*段)',flags=re.I) 
pattern10=re.compile(r'(^|[^a-zA-Z长短低高等脂水])T(\d{1,2})(?!.*[段_信号压黑为呈示a-zA-Z])',flags=re.I) 
pattern13=re.compile(r'(^|[^a-zA-Z])T(\d{1,2})椎',flags=re.I) 
pattern14=re.compile(r'(^|[^a-zA-Z])T([3-9]|10|11|12)(?!.*[MN])',flags=re.I) 
pattern11=re.compile(r'(^|[^a-zA-Z])S([1-5])(?!.*[段a-zA-Z0-9])',flags=re.I) 
pattern12=re.compile(r"([a-zA-Z\u4e00-\u9fa5])\.([a-zA-Z\u4e00-\u9fa5])",flags=re.I) 
NormKey_pattern=re.compile(NormKeyWords,flags=re.I) 
#%%预处理
def Str_replace(Str, title=False):
    """用替换方式预处理."""
    if title:
        Replace_table= PartReplaceTable
    else:
        Replace_table= ReplaceTable
    # 一般处理
    if type(Str) != str:
        return ''
    Str = re.sub("[ \xa0\x7f]", "",Str)
    for row in Replace_table:
        if row['原始值'] is np.nan:
            continue
        if row['替换值'] is np.nan:
            Str = Str.replace(row["原始值"], "")
        else:
            Str = Str.upper().replace(row["原始值"], row["替换值"])

    Str = pattern12.sub(r"\1。\2", Str)
    # 特殊处理
    
    sentence_end = [match.start()
                    for match in re.finditer(sentence_pattern, Str)]
    if sentence_end == []:
        sentence_end = [len(Str)]
    cstops = [0]
    cstops.extend(sentence_end)
    
    for i in range(len(cstops)-1):
        temp = Str[cstops[i]:cstops[i+1]]
        if temp=="":
            continue
        if re.search(spine_words, temp):
            temp = pattern9.sub('\\1颈\\2',temp)
            temp = pattern10.sub('\\1胸\\2',temp)
            temp = pattern13.sub('\\1胸\\2',temp)
            temp = pattern11.sub('\\1骶\\2',temp)
        temp = pattern14.sub('\\1胸\\2',temp)
        if title==False:
            for row in ConditionReplaceTable:
                if row['替换值'] is np.nan or row['原始值'] is np.nan:
                    continue
                temp=re.sub(row['原始值'],row['替换值'],temp)
        Str = Str.replace(Str[cstops[i]:cstops[i+1]], temp)
    return Str

def spine_extend(Str):
    """扩展椎体简写形式."""
    
    mat=pattern8.findall(Str)  
    if not mat:
        return Str
    try:
        for group in mat:
            new_str=""
            if group[0]==group[2] or group[2]=='':
                last=int(group[3])
            else:
                last=last_spine(group[0])
            start=int(group[1])
            end=int(group[3])
            for i in range(start,last+1):
                new_str+=group[0]+str(i)+"椎体、"
            if group[0]!=group[2] and group[2]!='':
                for i in range(1,end+1):
                    new_str+=group[2]+str(i)+"椎体、"
            old_str=group[0]+group[1]+"-"+group[2]+group[3]+group[4]
            Str=Str.replace(old_str,new_str[:-1])
    except:
        pass
    return Str

def last_spine(spine_str):
    if spine_str in "颈cC":
        last=7
    elif spine_str in "胸tT":
        last=12
    elif spine_str in "腰tT":
        last=5
    elif spine_str in "骶sS":
        last=5
    else:
        last=3
    return last

def disk_extend(Str):
    """扩展椎间盘简写形式."""
    mat=pattern7.findall(Str)  
    if not mat:
        return Str
    try:
        for group in mat:
            new_str=''
            if group[0]==group[4] or group[4]=='':
                last=int(group[5])
            else:
                last=last_spine(group[0])
            start=int(group[1])
            #下一段
            end=int(group[5])
            for i in range(start,last+1):
                new_str+=group[0]+str(i)+"/"+str(i+1)+"、"
            if group[0]!=group[4] and group[4]!='':
                for i in range(1,end+1):
                    new_str+=group[4]+str(i)+"/"+str(i+1)+"、"
            new_str=re.sub("[颈|c]7/8","颈7/胸1",new_str,flags=re.I)
            new_str=re.sub("[胸|t]12/13","胸12/腰1",new_str,flags=re.I)
            new_str=re.sub("[腰|l]5/6","腰5/骶1",new_str,flags=re.I)
            old_str=group[0]+group[1]+"/"+group[2]+group[3]+"-"+group[4]+group[5]+"/"+group[6]+group[7]
            Str=Str.replace(old_str,new_str[:-1])
    except:
        pass
    return Str

def extend_spine_dot(sentence):  
    """扩展椎体+顿号形式."""
    n=0
    sentence=pattern1.sub(r"\1\4\2、\4\3",sentence)
    sentence=pattern3.sub(r"\1\6\2\3、\6\4\5",sentence)
    while n<10:
        new_sentence=pattern2.sub(r"\1\3\2、\3\4",sentence)
        new_sentence=pattern4.sub(r"\1\4\2\3、\4\5\6",new_sentence)
        new_sentence=pattern5.sub(r"\1\2\3、\1\4",new_sentence)
        new_sentence=pattern6.sub(r"\1\2、\3",new_sentence)
        if new_sentence==sentence:
            break
        else:
            sentence=new_sentence
        n+=1
    return sentence
# %% 判断坐标区间相交

def Interval_cross(a, b, extend=False):
    if len(a) < 2 or len(b) < 2:
        return False
    if extend:
        a_start = a[0] % 100 if a[0] < 500 else a[0]
        a_end = a[1] % 100 if a[1] < 500 else a[1]
        b_start = b[0] % 100 if b[0] < 500 else b[0]
        b_end = b[1] % 100 if b[1] < 500 else b[1]
    else:
        a_start = a[0]
        a_end = a[1]
        b_start = b[0]
        b_end = b[1]
    if abs(a_start-b_start) > 100:
        return False
    if a_start < b_end:
        return a_end > b_start
    else:
        return b_end > a_start
# print(Interval_cross((505.5,508), (305,306)))
def find_max_common_words(list_a, list_c):
    # 初始化最大公共单词计数和对应的子列表集合
    max_common_count = 0
    best_lists = []

    for sublist in list_c:
        # 计算当前子列表与list_a的重复单词数量
        common_count = len(set(sublist['partlist']) & set(list_a['partlist']))
        
        # 如果找到新的最大值，重置best_lists并添加当前子列表
        if common_count > max_common_count:
            max_common_count = common_count
            best_lists = [sublist]
        
        # 如果当前计数等于最大值，则将当前子列表添加到结果中
        elif common_count == max_common_count:
            best_lists.append(sublist)

    return best_lists


def find_measure(Str):  # 提取测量值
    Str = Str.replace("*", "×")
    relink =  r'(\d+(\.\d+)?(?:mm|cm|m|\*|×))(?![a-zA-Z])|(\d+(\.\d+)?(?:毫米|米))' 
    mes = re.findall(relink, Str, flags=re.I)
    maxVal = 0.0
    value = 0.0
    percent = 0.0
    volume=0.0
    unit = ""
    positive=False
    mes=[x for group in mes for x in group if x!='']
    for x in reversed(mes):
        positive=True
        if x=='':
            continue
        if unit != "" and "×" in x:
            x = x.replace("×", unit)
        i = x.lower().find("cm")
        if i < 0:
            i = x.find("厘米")
        if i >= 0:
            try:
                value = (float(x[:i]))*10
                unit = 'cm'
            except:
                pass
        else:
            i = x.lower().find("mm")
            if i < 0:
                i = x.find("毫米")
            if i >= 0:
                try:
                    value = (float(x[:i]))
                    unit = 'mm'
                except:
                    pass
            else:
                i = x.lower().find("m")
                if i < 0:
                    i = x.find("米")
                if i >= 0:
                    try:
                        value = (float(x[:i]))*100
                        unit = 'm'
                    except:
                        pass
        if value > maxVal:
            maxVal = value
    #提取百分比值
    relink = r'[\d\.]{1,}(?:%|％)'
    v = (re.findall(relink, Str))
    if v:
        percent = float(v[0][:-1])/100
        positive=True
    #提取体积值
    relink =  r'(\d+(\.\d+)?(?:ml|毫升))(?![a-zA-Z])' 
    mes = re.findall(relink, Str, flags=re.I)
    mes=[x for group in mes for x in group if x!='']   
    if mes:
        positive=True
        volume= float(mes[0][:-2])
    #判断阳性
    for index,row in nomalMeasure.iterrows():
        if type(row['关键词'])!=str:
            continue
        if row['属性']=="长度" and maxVal>0:
            if maxVal>=row['最小值'] and maxVal<=row['最大值'] and re.search(row['关键词'],Str):
                 positive=False
        if row['属性']=="百分比" and percent>0:
            if percent>=row['最小值'] and percent<=row['最大值'] and re.search(row['关键词'],Str):
                 positive=False
        if row['属性']=="体积" and volume>0:
            if volume>=row['最小值'] and volume<=row['最大值'] and re.search(row['关键词'],Str):
                 positive=False
    return (maxVal, percent,volume,positive)


def get_positive(item, debug=False):
    # """判断句子阳性阴性."""
    positive = False
    item['measure'],item['percent'],item['volume'],positive = find_measure(item['primary'])
    if item['measure'] > 0 or item['percent']>0 or item['volume'] > 0:
        return positive, item['measure'], item['percent'],item['volume']
    if re.search(ignore_keywords, item['primary']):
        return False, 0, 0,0
    sentence_list = re.split(",", re.sub(',现|,拟|,考虑', "", item['illness']))
    # sentence_list=re.split("[,，]",item['illness'])
    sentence_list=[re.sub(stopwords, "", x,flags=re.I) for x in sentence_list ]
    for item in sentence_list:
        if debug:
            print("item=", item)
        # print(len(item))
        if len(item) == 0:
            continue
        if item in absolute_illness:
            if debug:
                print(absolute_illness)
            return True, 0.0, 0.0, 0.0
        if item in absolute_norm.split("|"):
            continue
        if item in sole_words.split("|"):
            if debug:
                print(item, "in", sole_words.split("|"))
            return True, 0.0, 0.0, 0.0
        if re.search(illness_words, item) != None:
            if debug:
                print(item, "in illness", re.search(illness_words, item))
            return True, 0.0, 0.0, 0.0
        if   NormKey_pattern.search(item) == None and len(item) > 1:
            if debug:
                print(item, "not in norm", NormKey_pattern.search(item))
            return True, 0.0, 0.0, 0.0
        else:
            if debug:
                print(item, " in norm", NormKey_pattern.search(item))
    return positive, 0.0, 0.0, 0.0


# primary = "胸腺区呈脂肪密度,未见增宽"
# sentence = "胸腺区呈脂肪密度,未见增宽"
# print(get_positive(primary, sentence, debug=True))


def starts_with_ignore(string):
    # 忽略句
    global Ignore_sentence
    if re.search(Ignore_sentence, string,re.I):
        return True
    else:
        return False

def GetPartTable(pre_ReportStr, keywords, stops):  # 通过关键词获取其他信息
    result = []
    i = 0
    for i in range(len(keywords)):
        k = keywords[i]
        info = {}
        start = 0
        end = len(pre_ReportStr)
        info['partlist'] = k[0][:-1]
        info['root'] = info['partlist'][0]
        info['axis'] = k[0][-1]
        temp = [x for x in stops if x <= k[1]]
        if temp != []:
            start = temp[-1]+1
        temp = [x for x in stops if x >= k[2]]
        if temp != []:
            end = temp[0]
            info['primary'] = pre_ReportStr[start:end].replace(" ", "")
        else:
            info['primary'] = pre_ReportStr[start:].replace(" ", "")
        # global ignore_keywords
        # info['ignore'] = any(info['primary'].startswith(element)
        #                     for element in ignore_keywords)
        info['ignore'] = starts_with_ignore(info['primary'])
        # print('primary=',info['primary'],"start=",start,"end=",end)
        info['words'] = pre_ReportStr[k[1]:k[2]]
        info['start'] = start
        info['word_start'] = k[1]
        info['word_end'] = k[2]
        info['sentence_end'] = end
        info['orientation'] = ''
        info['ambiguity'] = False
        search_str = pre_ReportStr[start:k[1]]
        # 从后往前搜索方位词
        mat = re.search("[左|右|两|双]", search_str[::-1])
        if mat:
            info['orientation'] = mat.group(0)
            if info['orientation'] == "两":
                info['orientation'] = "双"
        else:
            if info['words']=="左心":
                info['orientation'] = "左"
            if info['words']=="右心":
                info['orientation'] = "右"
        result.append(info)
    return result

# @timing_decorator
def padding_sentence(dict_list, pre_ReportStr, stops):
    # If the length of the dataframe is 1 and the sentence end is before the last stop,
    # and the sentence doesn't start with ignore, then update the sentence end and primary columns
    if len(dict_list) == 1:
        if dict_list[0]["sentence_end"] < stops[-1]:
            if not starts_with_ignore(pre_ReportStr[dict_list[0]["sentence_end"]+1:stops[-1]]):
                dict_list[0]["sentence_end"] = int(stops[-1])
                dict_list[0]["primary"] = pre_ReportStr[dict_list[0]
                                                        ['start']:stops[-1]].replace(" ", "")
        # Convert the list of dictionaries back to a dataframe and return it
        return dict_list

    # Get a list of unique sentence start and end positions, and sort them
    sentence_list = list(
        set([d['start'] for d in dict_list] + [d['sentence_end'] for d in dict_list]))
    sentence_list.sort()

    # If there are at least two sentences
    if len(sentence_list) >= 2:
        n = 1
        # Loop through each sentence pair
        while n <= len(sentence_list)-1:
            # If it's the last sentence pair, only consider stops after the last sentence end
            if n == len(sentence_list)-1:
                stoplist = [x for x in stops if x > sentence_list[n]]
            # Otherwise, consider stops between the current and next sentence
            else:
                stoplist = [x for x in stops if x >
                            sentence_list[n] and x < sentence_list[n+1]]

            # If there are stops between the sentences and the current sentence doesn't start with ignore,
            # loop through each stop and update the sentence end and primary columns
            if stoplist != [] and (pre_ReportStr[sentence_list[n]] not in "。;；？\n\r"):
                for x in stoplist:
                    if starts_with_ignore(pre_ReportStr[sentence_list[n]+1:x]):
                        break
                    for d in dict_list:
                        if d["start"] == sentence_list[n-1]:
                            d["sentence_end"] = int(x)
                            d["primary"] = pre_ReportStr[sentence_list[n-1]:x].replace(" ", "")
                    if pre_ReportStr[x] in "。;；？\n\r":
                        break
            n += 2

    # Convert the list of dictionaries back to a dataframe and return it
    return dict_list

# @timing_decorator
# 同一句子中，若同时存在同一部位的父节点和子节点，只保留最深的子节点
def merge_part(data_dict, pre_ReportStr, title=False):
    # Get a set of all sentence start positions
    data_dict = [dict(t)
                 for t in {tuple(d.items()) for d in data_dict}]
    sentence_start = set(row['start'] for row in data_dict)

    # Create an empty list to store the processed data
    data = []

    # Loop through each sentence start position
    for start in sentence_start:
        # Get all rows with the current start position
        sentence = [row for row in data_dict if row['start'] == start]

        # Add a new key 'merge' to each row and set all values to False
        for row in sentence:
            row['merge'] = False

        # Remove the last character of the 'primary' field if it's a period or comma
        if sentence[0]['primary'][-1] == '.' or sentence[0]['primary'][-1] == ',':
            sentence[0]['primary'] = sentence[0]['primary'][:-1]

        # If there's only one row, append it to the processed data and continue to the next start position
        if len(sentence) == 1:
            data.append(sentence[0])
            continue

        # If 'title' is False, sort the rows by 'partlist_length' in descending order
        # and merge the ones with the same orientation and a superset relationship
        if not title:
            sentence.sort(key=lambda x: x['partlist_length'], reverse=True)
            for m in range(len(sentence)-1):
                if sentence[m]['merge'] == True:
                    continue
                for n in range(m+1, len(sentence)):
                    if (set(sentence[m]['partlist']) >= set(sentence[n]['partlist']) and
                            sentence[m]['orientation'] == sentence[n]['orientation'] and
                            sentence[m]['positive'] == sentence[n]['positive']):
                        sentence[n]['merge'] = True
        # If 'title' is True, sort the rows by 'partlist_length' in ascending order
        # and merge the ones with the same orientation and a subset relationship
        else:
            sentence.sort(key=lambda x: x['partlist_length'])
            for m in range(len(sentence)-1):
                if sentence[m]['merge'] == True:
                    continue
                for n in range(m+1, len(sentence)):
                    punctStr = pre_ReportStr[sentence[m]
                                             ['word_end']:sentence[n]['word_start']]
                    if re.search("[\\|/|+]", punctStr):
                        if (set(sentence[m]['partlist']) >= set(sentence[n]['partlist']) and
                                sentence[m]['orientation'] == sentence[n]['orientation']):
                            sentence[n]['merge'] = True
                    else:
                        if (set(sentence[m]['partlist']) <= set(sentence[n]['partlist']) and
                                sentence[m]['orientation'] == sentence[n]['orientation']):
                            sentence[m]['merge'] = True
                            break

        # Append the rows with 'merge' set to False to the processed data
        for row in sentence:
            if row['merge'] == False:
                data.append(row)

    # Convert the processed data to a DataFrame, sort it by 'start' and 'word_start' columns, and reset the index
    data = sorted(data, key=lambda x: (x['start'], x['word_start']))
    # df_process = df_process.reset_index(drop=True)

    # Return the processed DataFrame
    return data

def get_illness(sentence, pre_ReportStr):
    """从句子中抽取表达疾病的字符串."""
    global punctuation
    illness = ''
    if len(sentence) == 0:
        return ""
    illness_start = sentence[-1]["word_end"]
    illness_end = sentence[-1]["sentence_end"]
    if illness_start < illness_end:
        # 常规illness定义为最后一个word_end之后到句子结尾的字符
        illness = re.sub(
            punctuation, "", pre_ReportStr[illness_start:illness_end])
        illness = re.sub("^\d[.|、]", "", illness)
        # 处理否定前置，如“未见颅脑异常”，illness=“未见”+“异常”
        if sentence[-1]["start"] < sentence[-1]["word_start"]:
            if re.search(deny_words, pre_ReportStr[sentence[-1]["start"]:sentence[-1]["word_start"]]):
                illness = re.sub(punctuation, "", pre_ReportStr[sentence[-1]["start"]:
                                                                sentence[-1]["word_start"]])+illness
    # 处理完全倒置，如“血肿位于肾脏”,illness定义为句子开始到第一个word_start之间的字符
    if re.sub(stopwords,"",illness) == ""  and sentence[0]["start"] < sentence[0]["word_start"]:
        front_illness = pre_ReportStr[sentence[0]["start"]:sentence[0]["word_start"]]
        if len(re.sub(stopwords,"",front_illness))>len(re.sub(stopwords,"",illness)):
            illness=front_illness
    # 处理头尾都是关键词的情况
    if len(sentence) > 1 and ((len(illness) <= 2 and NormKey_pattern.search(illness)==None and illness not in sole_words) or illness==''):
        #mid_illness = pre_ReportStr[sentence[0]["word_end"]:sentence[-1]["word_start"]]
        for i in range(len(sentence)-1):
            mid_illness=pre_ReportStr[sentence[i]["word_end"]:sentence[i+1]["word_start"]]
            mid_illness=re.sub(punctuation, "",mid_illness)
            if len(mid_illness) >= 2:
                illness = mid_illness
                break
    if illness!='' and illness[0]==",":
        illness=illness[1:]
    return illness.replace(" ","")

def get_ambiguity(sentence) -> tuple:
    # convert DataFrame to list of dictionaries
    # sentence = sentence.to_dict('records')

    ambiguity_sentence = []
    solo_sentence = []
    word_end = sentence[0]['word_end']

    ambiguity_sentence = [s for s in sentence if s["word_start"] < word_end ]
    sentence = [s for s in sentence if s not in ambiguity_sentence]

    longest_word = max(len(word['words']) for word in ambiguity_sentence)
    ambiguity_sentence = [word for word in ambiguity_sentence if len(
        word['words']) == longest_word]
    ambiguity_sentence = drop_dict_duplicates(ambiguity_sentence, ['partlist'])

    if len(ambiguity_sentence) == 1:
        solo_sentence = ambiguity_sentence
        ambiguity_sentence = []
    else:
        for word in ambiguity_sentence:
            word['ambiguity'] = True

    return sentence, solo_sentence, ambiguity_sentence

def xmerge(a, b):
    """将两个列表穿插组合."""
    alen, blen = len(a), len(b)
    mlen = max(alen, blen)
    for i in range(mlen):
        if i < alen:
            yield a[i]
        if i < blen:
            yield b[i]

# @timing_decorator
def clean_mean(data_dict, pre_ReportStr, add_info):
    for i, d in enumerate(data_dict):
        partlist_length = len(d['partlist'])
        data_dict[i]['partlist_length'] = partlist_length
        data_dict[i]['index'] = i
    global punctuation
    df_process = []
    ambiguity_list = []
    sentence_start = set([d['start'] for d in data_dict])
    # Loop over sentence_start list

    for start in sentence_start:
        # Get all rows with the current start position
        sentence = [row for row in data_dict if row['start'] == start]
        sentence.sort(key=lambda x: x['word_start'], reverse=False)
        if len(sentence) == 1:
            df_process += sentence
            continue

        while len(sentence) > 0:
            sentence, solo_sentence, ambiguity_sentence = get_ambiguity(
                sentence)
            df_process += solo_sentence
            if len(ambiguity_sentence) > 0:
                ambiguity_list.append(ambiguity_sentence)
    clean_sentence = clean_mean_step2(df_process, ambiguity_list, add_info)
    clean_sentence_list = clean_mean_step3(
        df_process, pre_ReportStr, clean_sentence)
    return clean_sentence_list

  
def clean_mean_step2(process_list, ambiguity_list, add_info):
    # Sort the process list by index
    process_list = sorted(process_list, key=lambda x: x['index'])

    # Create an empty list to store the disambiguated parts
    clean_sentence = []

    # Iterate over each item in the ambiguity list
    for ambiguity in ambiguity_list:
        ambiguity_find = False
        if re.search(spine_words,ambiguity[0]['primary']):
            ambiguity=[x for x in ambiguity if "女性附件" not in x['partlist']]
        # 参考检查部位
        temp=[]
        if  add_info:
            for part_info in add_info:
                temp.extend( [x for x in ambiguity if Interval_cross(x['axis'], part_info) ])
            if len(temp) >0 and "脊柱" not in [x['root'] for x in temp] and "皮肤软组织" not in [x['position'] for x in temp]:
                clean_sentence.extend(temp)
                ambiguity_find = True
        
        # Find the indices of parts that come before and after the current ambiguity            
        if not ambiguity_find:
            previous_list = [x['index']
                            for x in process_list if x['index'] < ambiguity[0]['index']]
            next_list = [x['index']
                        for x in process_list if x['index'] > ambiguity[-1]['index']]
            search_list = [i for i in xmerge(previous_list[::-1], next_list)]
            # Iterate over each adjacent part and try to disambiguate the current part
            for n in search_list:
                adjacentPart = [p for p in process_list if p['index'] == n][0]
                if re.search(spine_words,adjacentPart['primary']):
                    ambiguity=[x for x in ambiguity if "女性附件" not in x['partlist']]
                # temp = [x for x in ambiguity if x['position'] in adjacentPart['partlist'] or 
                #                                 adjacentPart['position'] in x['partlist']]
                #找出与相邻部位最匹配的多义词
                temp= find_max_common_words(adjacentPart,ambiguity)
                #关键词算法查找失败(n=0)或者不能去掉混淆词（n>1）的情况下，以坐标为基准再次查找
                if len(temp) == 0 or len(temp)>1:
                    adjacent = [
                        p for p in process_list if p['index'] == n][0]['axis']
                    temp = [x for x in ambiguity if Interval_cross(
                        x['axis'], adjacent)]
                #查找成功，添加到clean_sentence。ambiguity_find=True表示不再进一步查找
                if len(temp) > 0 and len(temp)<len(ambiguity):
                    clean_sentence.extend(temp)
                    ambiguity_find = True
                    break
        
        # 如果以上没有匹配，则扩展坐标范围再次匹配
        if not ambiguity_find:
            for n in search_list:
                adjacentPart = [
                    p for p in process_list if p['index'] == n][0]['partlist']
                temp = [x for x in ambiguity if Interval_cross(
                    x['axis'], adjacent, extend=True)]
                if len(temp) > 0:
                    clean_sentence.extend(temp)
                    ambiguity_find = True
                    break
        # 如果以上没有匹配，则扩展部位坐标范围再次匹配
            if not ambiguity_find:
                for part_info in add_info:
                    temp = [x for x in ambiguity if Interval_cross(
                        x['axis'], part_info, extend=True)]
                    if len(temp) > 0:
                        clean_sentence.extend(temp)
                        ambiguity_find = True
        # 若没有上下文/附加信息可以消解歧义的处理
        if not ambiguity_find:
            # 优先部位作为根节点
            priority = [x for x in ambiguity if re.search(
                second_root, x['position'])]
            if len(priority) > 0:
                ambiguity[0]['partlist'] = tuple([priority[0]['position']])
                ambiguity[0]['root'] = priority[0]['position']
                ambiguity[0]['position'] = priority[0]['position']
                clean_sentence.append(ambiguity[0])
            else:
                ambiguity = [x for x in ambiguity if x['partlist_length'] > 1]
                # 同时属于多个根节点的部位，全部保留
                second_part = [x['partlist'][1] for x in ambiguity]
                if len(set(second_part)) == 1:
                    clean_sentence.extend(ambiguity)
                else:
                    # 分词不同的部位，保留位置靠前，word_start较小的
                    start_last = max([x['word_start'] for x in ambiguity])
                    start_first = min([x['word_start'] for x in ambiguity])
                    if start_last > start_first:
                        ambiguity = [
                            x for x in ambiguity if x['word_start'] == start_first]
                        clean_sentence.append(ambiguity[0])
                    else:
                        clean_sentence.extend(ambiguity)
    return clean_sentence

def clean_mean_step3(df_process_list, pre_ReportStr, clean_sentence_list):
    # Convert DataFrames to list of dictionaries
    df_process_list += clean_sentence_list
    df_process_list = sorted(df_process_list, key=lambda x: x['index'])
    sentence_start = set([x['start'] for x in df_process_list])
    clean_sentence_list = []

    for start in sentence_start:
        sentence = [x for x in df_process_list if x['start'] == start]
        illness = ""
        replacement = re.sub("^\d[.|、]", "", sentence[0]['primary'])
        for s in sentence:
            s['primary'] = replacement
        if len(sentence) > 1:
            sentence = sorted(sentence, key=lambda x: x['word_start'])
            temp = []
            # "处理包含提示词的特殊句型，如胸廓入口水平见食道软组织结节，只提取食道软组织结节，忽略前面的方位定语"
            tip_sentence = []
            for mat in re.finditer(tipwords, sentence[0]['primary']):
                if mat:
                    tip_sentence = [x for x in sentence if x['word_start'] < (sentence[0]['start'] + mat.end())]
                    if tip_sentence != []:
                        # temp = [x for x in sentence if x['position'] not in [y['position'] for y in tip_sentence]]
                        temp= [x for x in sentence if x['word_start'] >= (sentence[0]['start'] + mat.end())]
                        break

            else:
                temp = sentence
            illness = get_illness(temp, pre_ReportStr)
            for item in temp:
                item['illness'] = illness
                item["positive"], item["measure"], item["percent"], item["volume"] = get_positive(item)
                if item['positive'] == True:
                    item['ignore'] = False
                clean_sentence_list.append(item)
            if temp == []:
                for item in tip_sentence:
                    item['illness'] = get_illness(tip_sentence, pre_ReportStr)
                    item["positive"], item["measure"], item["percent"], item["volume"] = get_positive(item)
                    if item['positive'] == True:
                        item['ignore'] = False
                    clean_sentence_list.append(item)
            else:
                for item in tip_sentence:
                    item['illness'] = ''
                    item['positive'] = False
                    item['measure'] = 0
                    item['percent'] = 0
                    item["volume"] =0
                    clean_sentence_list.append(item)
        else:
            illness = get_illness(sentence, pre_ReportStr)
            sentence[0]['illness'] = illness
            sentence[0]["positive"], sentence[0]["measure"], sentence[0]["percent"], sentence[0]["volume"] = get_positive(sentence[0])
            if sentence[0]['positive'] == True:
                sentence[0]['ignore'] = False
            clean_sentence_list.append(sentence[0])
    # Convert list of dictionaries back to DataFrame
    return clean_sentence_list

def fill_orientation(data_dict,pre_ReportStr):
    """"填充无方向的部位"""
    # global sentence_pattern
    # sentence_end = [match.start()
    #             for match in re.finditer(sentence_pattern, pre_ReportStr)]
    for i, part in enumerate(data_dict):
        if part['orientation']=='' and re.search(dualparts," ".join(part['partlist'])):
            # previous_end=[x for x in sentence_end if x<part['start']]
            # if previous_end==[]:
            #     break
            for o in data_dict[i::-1]:
                # if o['sentence_end']<=previous_end[-1]:
                #     break
                if o['orientation']!="":
                    data_dict[i]['orientation']=o['orientation']
                    break
    return data_dict

def get_orientation_position(ReportStr: str, debug=False, title=False, match=False, add_info=[]):
    """实体抽取主函数."""
    if debug:
        start_time = time.time()
    #脊柱简写预处理
    if type(ReportStr)!=str or len(ReportStr)==0:
        return []
    ReportStr=extend_spine_dot(spine_extend(disk_extend(ReportStr)))
    #print(ReportStr)
    pre_ReportStr = Str_replace(ReportStr, title)

    global stop_pattern
    result = []
    if len(pre_ReportStr) == 0:
        return result
    if not (re.search(stop_pattern, pre_ReportStr[-1])):
        pre_ReportStr = pre_ReportStr+'\n'
    stops = [match.start()
             for match in re.finditer(stop_pattern, pre_ReportStr)]
    # sentences=re.split(stop_pattern,ReportStr)
    if match:
        KGgraph = title_knowledgegraph
    else:
        KGgraph = knowledgegraph
    for kg in KGgraph:
        BodyProcessor=None
        BodyProcessor = KeywordProcessor()
        BodyProcessor.add_keywords_from_dict(kg)
        allk=BodyProcessor.get_all_keywords()
        keywords = BodyProcessor.extract_keywords(
            pre_ReportStr, span_info=True)
        if keywords != []:
            # print("kg=",kg)
            # print("keyword=",keywords)
            temp = GetPartTable(pre_ReportStr, keywords, stops)
            result += temp
    if len(result) == 0:
        return []
    result = sorted(result, key=lambda x: (x['start'], x['word_start']))
    # start_index=list(dict.fromkeys([x['start'] for x in result]))
    # sentence_index=dict(zip(start_index, sentences))
    for i, d in enumerate(result):
        result[i]['position'] = d['partlist'][-1]

    result = padding_sentence(result, pre_ReportStr, stops)
    result = clean_mean(result, pre_ReportStr, add_info)
    result = merge_part(result, pre_ReportStr, title)

    if title:
        for d in result:
            d['deny']=False
            if d['orientation'] != '':
                continue
            if re.search("左(?![侧斜])",d['illness']) and d['orientation'] == '':
                d['orientation'] = '左'
            if re.search("右(?![侧斜])",d['illness']) and d['orientation'] == '':
                d['orientation'] = '右'
            if re.search("双(?![侧斜])",d['illness']) and d['orientation'] == '':
                d['orientation'] = '双'
    else:
        for d in result:
            d['deny']=True if re.search(deny_words,d['illness']) else False
    result=fill_orientation(result,pre_ReportStr)             
    result = [{k: v for k, v in d.items() if k not in ["word_end",
                                                       "sentence_end", "partlist_length", "merge"]} for d in result]

    if debug:
        end_time = time.time()
        print("analysis time=%.3f秒" % (end_time-start_time))
    return result

def drop_dict_duplicates(list_of_dicts, keys):
    seen = set()
    result = []
    for d in list_of_dicts:
        dict_key = tuple(d[key] for key in keys)
        if dict_key not in seen:
            seen.add(dict_key)
            result.append(d)
    return result
# In[33]:


if __name__ == "__main__":
    ReportStr = """
    急诊报告： 与2023/1/7日片比较: 两肺多发斑片渗出实变影，边界不清,内见空洞形成
    双侧胸腔少量积液与前相仿，双肺下叶膨胀不全，右肺下叶较前改善；左侧斜裂胸膜积液较前减少。
    双肺见多发片状模糊影及片状影，部分实变。双肺下叶部分支气管狭窄，余气管及主要支气管通畅。
    未见左侧肺门及右纵隔增大淋巴结。心脏增大，心腔密度减低，主动脉、冠状动脉钙化；心包少量积液。
    附见：右侧部分肋骨陈旧性骨折。
    与2022/8/23日片比较: 肝脏增大。肝实质密度均匀，肝左外叶见低密度灶。无肝内外胆管明显扩张。肝脾周围可见积液；
    腹腔内脂肪间隙稍模糊。 胆囊内可见团片状稍高密度影，范围约53×19mm，形态不规则。
    胰腺形态大小、密度未见异常，胰管未见明显扩张。 脾脏形态、大小、密度未见明确异常。
    双肾形态、大小、密度未见明显异常，双侧肾盂、肾盏未见明显扩张积水。 膀胱欠充盈显示不清。
    前列腺形态、大小及密度未见异常。 小肠稍积液；腹主动脉及双侧髂动脉钙化。腹膜后未见明显增大淋巴结。盆腔少量积液。
    腰椎骨质增生。 附见：心脏增大，心腔密度减低，CT值约31HU；主动脉及冠脉钙化；心包积液。右下肺节段性体积缩小。
    与2022/6/23日片比较: 双侧基底节区少许小斑点状低密度影，余脑实质内未见异常密度影。脑沟稍增宽，腔内无异常密度影。
    颅内中线结构居中。双侧颈内动脉颅内段可见钙化,边界不清。
    """

    # ReportStr = """1.前上纵隔术后改变，双肺多发小结节，以磨玻璃密度为主，大致同前，建议结合临床随诊复查。左膈面明显抬高。
    # 2.双肺新见多发斑片状模糊影，考虑感染，请结合临床。
    # 3.附见：肝内低密度影；甲状腺右叶结节，大致同前。"""
    # ReportStr = """
    # 1.颈4/5椎间盘轻微膨出，颈椎退行性变。 2.胸12椎体压缩性改变；胸椎终板变性，胸椎轻度退行性变。 3.腰椎退行性变；腰4/5椎间盘轻微膨出。 4.骶尾椎MRI未见明显异常征象。 5.胸、腰及臀部皮下软组织肿胀、大片水肿；双侧胸腔积液；盆腔少量积液。

    # """
    # ReportStr = "肝胆脾：肝左叶低密度灶，所见如上述，必要时进一步检查，详请贵科阅片并密切结合临床考虑。"
    # ReportStr = "右胸锁关节较对侧稍肿胀并向前突出，双锁骨骨质未见明显异常，请结合临床。"
    # ReportStr = "双侧前根囊肿，退行性变"
    # ReportStr = "肝胆系：胆囊可见结石"

    ReportStr = """胆囊壁略肿胀"""
    StudyPart = """胸部/肺平扫"""
#     ReportStr = """
# 第腰2-4椎体，第2/3,3/4,4/5腰椎间盘，颈2,3,4椎体骨折
#     """
    # studypart_analyze = get_orientation_position(StudyPart, title=True)
    df = get_orientation_position(ReportStr)
    # df = get_orientation_position(ReportStr)
    # pprint(studypart_analyze,compact=True)
    # pprint([d["orientation"]+" "+",".join(d['partlist'])+":"+d['illness'] +" positive="+str(d['positive']) for d in  df])
    #print(disk_extend(ReportStr))
    # print(find_measure("胆总管直径17mm"))
    # studypart_analyze = get_orientation_position(StudyPart, title=True)

    # ReportStr = "胆囊不大，颈部见致密影"
    # df = get_orientation_position(StudyPart, title=True)
    # df = get_orientation_position(ReportStr, add_info=[s['axis'] for s in studypart_analyze])
    pprint(df)
    # df = get_orientation_position(ReportStr)

# In[35]:



# if __name__ == "__main__":  # 批量样例验证
#     report = pd.read_excel("报告样本.xlsx")
#     report = report.drop_duplicates(['描述', '结论'])
#     report = report.reset_index()
#     #report.to_excel("报告样本去重.xlsx")
#     print(datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
#           '已读取文件%s条' % len(report.index))
#     df = []

#     start_time = time.time()
#     for index, row in report.iterrows():
#         studypart = get_orientation_position(row['部位'], title=True)
#         if len(studypart) > 0:
#             partlist = list(set([x['axis'] for x in studypart]))
#         temp = pd.DataFrame([])
#         temp = get_orientation_position(row['描述'], add_info=partlist)
#         if len(temp) == 0:
#             print("omission=", row['描述'])
#         temp = get_orientation_position(row['结论'], add_info=partlist)
#         if len(temp) == 0:
#             print("omission=", row['结论'])

#         if len(temp) > 0:
#             temp = [{**dic, '影像号': row['影像号']} for dic in temp]
#             df.extend(temp)
#         if index % 1000 == 0:
#             print(datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
#                   "%s//%s" % (index, len(report)))
#             if index > 0:
#                 end_time = time.time()
#                 print("  period=%.2f秒,速度=%.2f秒/条" %
#                       ((end_time-start_time), (end_time-start_time)/1000))
#                 start_time = time.time()
#             else:
#                 start_time = time.time()
#     df = pd.DataFrame(df, columns=list(df[0].keys()))
#     sum = len(df)
#     print(f"analyzed: {sum}")
#     df.to_excel("结构化数据库1.xlsx", index=False)
    
# %%提取肺结节
# if __name__ == "__main__":  # 批量样例验证
#     report = pd.read_excel("d:\\胸部体检.xlsx")
#     report = report.drop_duplicates(['描述', '结论'])
#     print(datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
#           '已读取文件%s条' % len(report.index))
#     df = pd.DataFrame([])
#     start_time = time.time()
#     for index, row in report.iterrows():
#         studypart = get_orientation_position(row['部位'], title=True)
#         if len(studypart) > 0:
#             partlist = list(set(studypart['axis'].tolist()))
#         temp = pd.DataFrame([])
#         temp = get_orientation_position(row['描述'], add_info=partlist)
#         if len(temp) == 0:
#             print("omission=", row['描述'])
#         if len(temp) > 0:
#             temp['report_text'] = row['描述']
#             temp['影像号'] = row['影像号']
#             temp = temp[(temp['illness'].str.find("结节") >= 0)]
#             df = df.append(temp, ignore_index=True)

#         if index % 1000 == 0:
#             print(datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
#                   "%s//%s" % (index, len(report)))
#             if index > 0:
#                 end_time = time.time()
#                 print("  period=%.2f秒,速度=%.2f秒/条" %
#                       ((end_time-start_time), (end_time-start_time)/1000))

#                 print(datetime.now().strftime(
#                     "%Y-%m-%d %H:%M:%S"), "saved %s" % len(df))
#                 start_time = time.time()
#             else:
#                 start_time = time.time()
#     sum = len(df)
#     print(f"analyzed: {sum}")
#     df.to_excel("肺结节.xlsx")
