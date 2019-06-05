#!/usr/bin/python
# -*- coding: UTF-8 -*-

import os
import struct# https://docs.python.org/2/library/struct.html
import sys
import traceback
import zlib# https://docs.python.org/2/library/zlib.html

# import chardet

class TopicStats:

    def __init__(self, topic, count, sum, max, min, max_body, min_body, max_message):
        self.topic = topic
        self.count = count
        self.sum = sum
        self.max = max
        self.min = min
        self.max_body = max_body
        self.min_body = min_body
        self.max_message = max_message
    
    def __repr__(self):
        return "%s: count=%d, sum=%d, avg=%d, max=%d, min=%d" \
            % (self.topic, self.count, self.sum, self.sum/self.count, self.max, self.min)


def parse_commitlog(store_base_dir):
    commitlog_dir = store_base_dir + '/commitlog'
    files = os.listdir(commitlog_dir)
    print(files)
    
    for file_name in files:
        commitlog_path = commitlog_dir + "/" + file_name
        topics = parse_commitlog_0(commitlog_path)

        if len(topics) == 0:
            print("NO message!")
        else:
            max = 0
            mt = None
            for t in topics.values():
                print(t)
                if t.max > max:
                    max = t.max
                    mt = t
            
            print("\n=====\nMAX OF ALL TOPICS:\n%s" % mt)
            print("\n=====\nMAX CONTENT:\n%s" % bytes2string(mt.max_body))
            # print("\n=====\nMAX MESSAGE:\n%s" % mt.max_message)


def parse_commitlog_0(commitlog_path):
    count = 0
    topics = {}
    with open(commitlog_path, mode='rb') as f:
        while True:
            success, temp_tup = parse_message(f)
            if not success:
                break

            count += 1
            if count % 100000 == 0:
                print(count)

            topic, body, message = temp_tup
            body_length = len(body)
            if topic not in topics:
                topics[topic] = TopicStats(topic, 1, body_length, body_length, body_length, body, body, message)
            else:
                topics[topic].count += 1
                topics[topic].sum += body_length
                if body_length > topics[topic].max:
                    topics[topic].max = body_length
                    topics[topic].max_body = body
                    topics[topic].max_message = message
                if body_length < topics[topic].min:
                    topics[topic].min = body_length
                    topics[topic].min_body = body
    
    print("count=%d" % count)
    return topics


# org.apache.rocketmq.store.CommitLog
MESSAGE_MAGIC_CODE = -626843481
BLANK_MAGIC_CODE = -875286124

# + 4 //TOTALSIZE
# + 4 //MAGICCODE
# + 4 //BODYCRC
# + 4 //QUEUEID
# + 4 //FLAG
# + 8 //QUEUEOFFSET
# + 8 //PHYSICALOFFSET
# + 4 //SYSFLAG
# + 8 //BORNTIMESTAMP
# + 8 //BORNHOST
# + 8 //STORETIMESTAMP
# + 8 //STOREHOSTADDRESS
# + 4 //RECONSUMETIMES
# + 8 //Prepared Transaction Offset
# + 4 + body_length //BODY
# + 1 + topic_length //TOPIC
# + 2 + properties_length //propertiesLength

# org.apache.rocketmq.common.sysflag.MessageSysFlag
COMPRESSED_FLAG = 1

def parse_message(f):

    msg_length, = struct.unpack('>I', f.read(4))
    if msg_length == 0:
        print("current position=%d, msg_length=%d, OVER!" % (f.tell(), msg_length))
        return False, None

    (magic_code, ) = struct.unpack('>i', f.read(4))
    if magic_code == 0 or magic_code != MESSAGE_MAGIC_CODE:
        print("current position=%d, msg_length=%d, magic_code=%d, OVER!" % (f.tell(), msg_length, magic_code))
        return False, None

    # f.seek(4 * 5 + 8 * 7, 1)
    body_crc, queue_id, flag, queue_offset, physical_offset, sys_flag, \
        born_timestamp, bh_ip1, bh_ip2, bh_ip3, bh_ip4, bh_port, \
            store_timestamp, sh_ip1, sh_ip2, sh_ip3, sh_ip4, sh_port, \
                reconsume_times, prepared_transation_offset \
                    = struct.unpack('>IIiQQiQBBBBIQBBBBIIQ', f.read(4 * 5 + 8 * 7))
    born_host = "%d.%d.%d.%d:%d" % (bh_ip1, bh_ip2, bh_ip3, bh_ip4, bh_port)
    store_host = "%d.%d.%d.%d:%d" % (sh_ip1, sh_ip2, sh_ip3, sh_ip4, sh_port)

    # body
    body_length, = struct.unpack('>I', f.read(4))
    body = f.read(body_length)
    if sys_flag == COMPRESSED_FLAG:
        body = zlib.decompress(body)

    # topic
    topic_length, = struct.unpack('>B', f.read(1))
    topic = f.read(topic_length).decode('ascii')

    (properties_length, ) = struct.unpack('>H', f.read(2))
    # f.seek(properties_length, 1)
    properties = f.read(properties_length).decode('utf8')

    calc_length = 4 * 7 + 8 * 7 + (4 + body_length) + (1 + topic_length) + (2 + properties_length)
    message = "calc_length=%d, msg_length=%d, magic_cod=%d, body_crc=%d, queue_id=%d, flag=%d, queue_offset=%d, "\
        "physical_offset=%d, sys_flag=%d, born_timestamp=%d, born_host=%s, store_timestamp=%d, store_host=%s, "\
        "reconsume_times=%d, prepared_transation_offset=%d, body_length=%d, body=%s, topic_length=%d, topic=%s, "\
        "properties_length=%d, properties=%s" \
        % (calc_length, msg_length, magic_code, body_crc, queue_id, flag, queue_offset, physical_offset, sys_flag,
        born_timestamp, born_host, store_timestamp, store_host, reconsume_times, prepared_transation_offset,
        body_length, bytes2string(body), topic_length, topic, properties_length, properties)

    return True, (topic, body, message)


def parse_consumequeue(store_base_dir, topic, queue_id):
    topic_consume_queue_dir = '%s/consumequeue/%s/%s' % (store_base_dir, topic, queue_id)
    commitlog_dir = store_base_dir + '/commitlog'

    for file_name in os.listdir(topic_consume_queue_dir):
        topic_consume_queue_file = topic_consume_queue_dir + '/' + file_name
        print('===== topic_consume_queue_file=%s' % topic_consume_queue_file)
        with open(topic_consume_queue_file, mode='rb') as f:
            while True:
                try:
                    success, temp_tup = parse_consumequeue_0(f)
                    if not success:
                        print('commitlog_offset=0, parse OVER!')
                        break
                    
                    commitlog_offset, = temp_tup
                    message = query_by_commitlog_offset(commitlog_offset, commitlog_dir)
                    print(message)

                except Exception as e:
                    print(e, traceback.format_exc())
                    break


def parse_consumequeue_0(f):
    commitlog_offset, message_size = struct.unpack('>QI', f.read(12))
    if commitlog_offset == 0:
        return False, None

    message_tag_hashcode = struct.unpack('>Q', f.read(8))[0]
    print('commitlog_offset=%d, message_size=%d, message_tag_hashcode=%d' 
        % (commitlog_offset, message_size, message_tag_hashcode))

    return True, (commitlog_offset)


def query_by_commitlog_offset(commitlog_offset, commitlog_dir):
    files = os.listdir(commitlog_dir)
    # print(files)

    commitlog_file_name = None
    begin_offset = -1
    for file_name in files:
        file_begin_offset = int(file_name)
        if commitlog_offset >= file_begin_offset and begin_offset < file_begin_offset:
            begin_offset = file_begin_offset
            commitlog_file_name = file_name

    # 消息已从 commitlog 中删除
    if not commitlog_file_name:
        return None

    commitlog_path = commitlog_dir + '/' + commitlog_file_name
    with open(commitlog_path, mode='rb') as f:
        f.seek(commitlog_offset - begin_offset, 0)
        success, tup = parse_message(f)# tup: topic, body, message
        if success:
            return tup[2]


def bytes2string(body):
    try:
        # <type 'str'>
        # print(type(body))
        # {'confidence': 0.99, 'encoding': 'utf-8'}
        # print(chardet.detect(body))
        return body.decode('utf8')
    except UnicodeDecodeError as e:
        print(e)
        return repr(e)


# 同 java.lang.String#hashCode
# s[0]*31^(n-1) + s[1]*31^(n-2) + ... + s[n-1]
def hashcode(string):
    h = 0
    for c in string:
        # print(ord(c), chr(ord(c)))
        h = 31 * h + ord(c)
    return h


# nohup python rocketmq_parser.py commitlog ~/store > commitlog.result &
# python rocketmq_parser.py commitlog /home/rocketmq/store
# python rocketmq_parser.py consumequeue ~/store ***topic 0 > commitlog.result
if __name__ == '__main__':
    kind = sys.argv[1]
    store_base_dir = sys.argv[2]

    if kind == 'consumequeue':
        topic = sys.argv[3]
        queue_id = sys.argv[4]
        parse_consumequeue(store_base_dir, topic, queue_id)
    elif kind == 'commitlog':
        parse_commitlog(store_base_dir)
