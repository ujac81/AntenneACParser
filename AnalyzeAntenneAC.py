#!/usr/bin/env python3
"""



"""

import json
import matplotlib.pyplot as plt
import requests
import time
from matplotlib.font_manager import FontProperties

from html.parser import HTMLParser

__author__ = 'ujansen'


class SongItem:
    def __init__(self, artist, title):
        self.artist = artist
        self.title = title

    def __hash__(self):
        return hash(str(self.artist+self.title))

    def __eq__(self, other):
        return self.artist == other.artist and self.title == other.title


class OptionHTMLParser(HTMLParser):
    """Record values of options in select element of an HTML page
    """

    def __init__(self, select):
        HTMLParser.__init__(self)
        self.options_table = []
        self.cur_select = ''
        self.select = select

    def reset_table(self):
        self.options_table = []

    def handle_starttag(self, tag, attrs):
        if tag == "select":
            self.cur_select = [x for x in attrs if x[0] == 'name'][0][1]
        if tag == "option" and self.cur_select == self.select:
            value = [x for x in attrs if x[0] == 'value'][0][1]
            self.options_table.append(value)


class PlaylistHTMLParser(HTMLParser):
    """Record table data in td elements of an HTML page

    td fields should be in tr fields of class 'bg1' and 'bg2'
    """

    def __init__(self):
        HTMLParser.__init__(self)
        self.playlist_table = []
        self.cur_table = []
        self.tr_classes = ['bg1', 'bg2']
        self.cur_class = ''
        self.rec_data = False

    def reset_table(self):
        self.playlist_table = []
        self.cur_table = []

    def handle_starttag(self, tag, attrs):
        """

        :param tag:
        :param attrs:
        """
        if tag == "tr":
            classes = [x for x in attrs
                       if x[0] == 'class' and x[1] in self.tr_classes]
            if len(classes) == 1:
                self.cur_class = classes[0][1]
            else:
                self.cur_class = ''
        if tag == "td" and self.cur_class in self.tr_classes:
            self.rec_data = True
        else:
            self.rec_data = False

    def handle_data(self, data):
        """

        :param data:
        :raise:
        """
        if self.rec_data:
            stripped = data.strip(' \n\t').replace('##amp;##', '&')
            if len(stripped) > 0:
                self.cur_table.append(stripped)

        # check that we have no double insert of time information --
        # might happen on crappy rows
        if len(self.cur_table) > 1:
            try:
                time.strptime(self.cur_table[1], "%H:%M:%S")
                # assume, that there was a crap line like
                # <td>00:00:00</td><td></td><td></td>
                # so drop out first item and retry
                self.cur_table = self.cur_table[1:]
            except ValueError:
                pass

        if len(self.cur_table) == 3:
            cur_tb = self.cur_table
            try:
                tt = time.strptime(cur_tb[0], "%H:%M:%S")
            except ValueError:
                print("Failed to convert %s to time data, "
                      "<td> parser must have failed!" % cur_tb[0])
                raise
            cur_tb[0] = tt.tm_hour*3600 + tt.tm_min*60 + tt.tm_sec
            self.playlist_table.append(cur_tb)
            self.cur_table = []


def get_selections(url):
    """Get available options for pl_day and pl_hour parameter for playlist on
    Antenne AC web page.

    :param url: playlist URL
    :return: [[pl_day values],[pl_hour values]]
    """
    r = requests.get(url)
    if r.status_code != 200:
        return []

    parser = OptionHTMLParser(select='pl_day')
    parser.feed(r.text)

    parser2 = OptionHTMLParser(select='pl_hour')
    parser2.feed(r.text)

    return [parser.options_table[::-1], parser2.options_table]


def get_playlist_for_day_and_hour(url, day, hour):
    """

    :param url:
    :param day:
    :param hour:
    :return:
    """
    print("Getting for %s - %s..." % (day, hour))
    r = requests.post(url, data={'pl_day': day, 'pl_hour': hour})
    if r.status_code != 200:
        return []

    text = r.text.replace('&', '##amp;##')  # & char will mess up html parser
    parser = PlaylistHTMLParser()
    parser.feed(text)

    return {'%s-%s' % (day, hour): parser.playlist_table}


def write_data_to_json_file(filename):
    """Create json object for each hour of day from antenne AC playlist
    information.

    JSON format: [ {"YYYY-MM-DD-HH" : [ [seconds-of-day, title, artist],
                                        ... ] } ]

    :param filename: json file name for write out
    """
    pl_url = 'http://www.antenne-ac.de/musik/playlist/'
    options = get_selections(url=pl_url)

    full_list = []
    for day in options[0]:
        for hour in options[1]:
            hour_list = get_playlist_for_day_and_hour(url=pl_url, day=day,
                                                      hour=hour)
            full_list.append(hour_list)

    data_str = json.dumps(full_list, indent=2)
    f = open(filename, 'w')
    f.write(data_str)
    f.close()


def read_data_from_json_file(filename):
    """Load playlist data from JSON file.

    :param filename: filename to read JSON object written by
                     write_data_to_json_file()
    :return: JSON format: [ {"YYYY-MM-DD-HH" :
                            [ [seconds-of-day, title, artist], ... ] } ]
    """
    f = open(filename, 'r')
    fdata = json.load(f)
    return fdata


def create_plain_data_table(json_obj):
    """Unfold JSON data object to plain data table: time-artist-title

    :param json_obj: JSON object in format from write_data_to_json_file()
    :return: [[time-in-seconds, artist, title]]
    """
    plain_list = []

    for hour_item in json_obj:
        songkey = list(hour_item.keys())[0]
        values = hour_item[songkey]
        for item in values:
            tt = int(time.mktime(time.strptime(songkey[:10], "%Y-%m-%d"))) + \
                item[0]
            plain_list.append([tt, item[2], item[1]])

    return plain_list


def create_occ_list(plain_data):
    """Create dict of song keys with list of time information

    :param plain_data: table from create_plain_create_plain_data_table()
    :return: [ {'MM/DD' : int }, { SongItem: [[time, day_time, map_days[day],
    day, day_time_str]] } ]
    """

    # collect all available dates and map to integer value
    map_days = {}
    for item in sorted(plain_data, key=lambda i: i[0]):
        day = time.strftime("%m/%d", time.localtime(item[0]))
        if day not in map_days:
            map_days[day] = len(map_days)

    occ_dict = {}

    for item in plain_data:
        songkey = SongItem(artist=item[1], title=item[2])
        day = time.strftime("%m/%d", time.localtime(item[0]))
        day_time_str = time.strftime("%H:%M:%S", time.localtime(item[0]))
        day_time = int(day_time_str[:2])*3600 + int(day_time_str[3:5]) * 60 \
            + int(day_time_str[-2:])
        app_item = [item[0], day_time, map_days[day], day, day_time_str]
        if songkey not in occ_dict:
            occ_dict[songkey] = [app_item]
        else:
            occ_dict[songkey].append(app_item)

    return [map_days, occ_dict]


def plot_occ(occ_list, map_days, num_ent=3):
    """

    """

    fontp = FontProperties()
    fontp.set_size('small')

    fig = plt.figure()
    ax = fig.add_subplot(111)
    ax.set_xticks(list(map_days.values()))
    ax.set_xticklabels(list(map_days.keys()))
    ax.set_yticks(range(24)[1:])

    colors = 'brykmgcw'
    markers = 'sovDp*+x'

    for i in range(num_ent):
        key, val = occ_list[i]
        x, y = [[], []]
        for item in val:
            x.append(item[2])
            y.append(item[1]/3600.)
        title = key.artist + ' - ' + key.title
        ax.scatter(x, y, c=colors[i % 8], marker=markers[i % 7], s=50,
                   label=title)

    plt.axis([-0.5, 6.5, 0, 24])
    plt.xlabel('day')
    plt.ylabel('hour of day')
    plt.grid(True)
    plt.title("AntenneAC %d most wanted" % num_ent)
    plt.legend(scatterpoints=1, loc='lower right', prop=fontp,
               )
    plt.show()


if __name__ == '__main__':
    # write_data_to_json_file('/tmp/antenne_ac_data.json')

    pl_data_in = read_data_from_json_file('/tmp/antenne_ac_data.json')
    pl_data_plain = create_plain_data_table(pl_data_in)
    map_days, occ_list = create_occ_list(pl_data_plain)

    occ_list = list(reversed(sorted(occ_list.items(),
                                    key=lambda item: len(item[1]))))

    plot_occ(occ_list, map_days, 5)
