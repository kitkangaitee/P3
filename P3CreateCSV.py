
# coding: utf-8

# <h1>Wrangling OSM file before creating CSV</h1>

# In[ ]:

import xml.etree.cElementTree as ET
import pprint
import collections
from collections import defaultdict
import re



# <h2>Counting the different types of tags</h2>

# In[ ]:

def count_tags(filename): #count the different types of tags
    tags = collections.Counter()
    for event, elem in ET.iterparse(filename):
        tags[elem.tag] += 1
    return tags


# In[ ]:

tags = count_tags('coquitlam.osm')
pprint.pprint(tags)


# <h2>Exploring Key types</h2>

# In[ ]:

lower = re.compile(r'^([a-z]|_)*$')
lower_colon = re.compile(r'^([a-z]|_)*:([a-z]|_)*$')
problemchars = re.compile(r'[=\+/&<>;\'"\?%#$@\,\. \t\r\n]')


def key_type(element, keys):
    if element.tag == "tag":
        k = element.attrib['k']
        if lower.search(k):
            keys["lower"] += 1
        elif lower_colon.search(k):
            keys["lower_colon"] += 1
        elif problemchars.search(k):
            keys["problemchars"] += 1
            print k
            print element.attrib['v']
        else:
            keys["other"] += 1
    return keys


def keys(filename):
    keys = {"lower": 0, "lower_colon": 0, "problemchars": 0, "other": 0}
    for _, element in ET.iterparse(filename):
        keys = key_type(element, keys)
    return keys


# In[ ]:

keys = keys('coquitlam.osm')
pprint.pprint(keys)


# <h2>Finding the number of unique users</h2>

# In[ ]:

def users(filename):
    users = set()
    for _, element in ET.iterparse(filename):
        if get_user(element):
            users.add(get_user(element))
    return users

def get_user(element):
    if element.get('uid'):
        uid=element.attrib['uid']
        return uid
    else:
        return None


# In[ ]:

users = users('coquitlam.osm')


# In[ ]:

len(users)


# <h2>Auditing Street Types</h2>

# In[ ]:

street_type_re = re.compile(r'\b\S+\.?$', re.IGNORECASE)


expected = ["Street", "Avenue", "Boulevard", "Drive", "Court", "Place", "Square", "Lane", "Road", 
            "Trail", "Parkway", "Commons", "Close", "Crescent", "Way", "Highway", "East" , "Mall", "North"]

mapping = { "St": "Street",
            "St.": "Street",
            "Ave": "Avenue",
            "Rd.": "Road",
            "Rd": "Road"
            }


def audit_street_type(street_types, street_name):
    m = street_type_re.search(street_name)
    if m:
        street_type = m.group()
        if street_type not in expected:
            street_types[street_type].add(street_name)


def is_street_name(elem):
    return (elem.attrib['k'] == "addr:street")


def audit(osmfile):
    osm_file = open(osmfile, "r")
    street_types = defaultdict(set)
    for event, elem in ET.iterparse(osm_file, events=("start",)):

        if elem.tag == "node" or elem.tag == "way":
            for tag in elem.iter("tag"):
                if is_street_name(tag):
                    audit_street_type(street_types, tag.attrib['v'])
    osm_file.close()
    return street_types


# In[ ]:

faulty_name = audit('coquitlam.osm')


# In[ ]:

faulty_name


# <h2>Cleaning data and creating csv</h2>

# In[ ]:

import csv
import codecs
import re
import xml.etree.cElementTree as ET

import cerberus
import schema
import io

OSM_PATH = "example.osm"

NODES_PATH = "nodes.csv"
NODE_TAGS_PATH = "nodes_tags.csv"
WAYS_PATH = "ways.csv"
WAY_NODES_PATH = "ways_nodes.csv"
WAY_TAGS_PATH = "ways_tags.csv"

LOWER_COLON = re.compile(r'^([a-z]|_)+:([a-z]|_)+')
PROBLEMCHARS = re.compile(r'[=\+/&<>;\'"\?%#$@\,\. \t\r\n]')

SCHEMA = schema.schema

# Make sure the fields order in the csvs matches the column order in the sql table schema
NODE_FIELDS = ['id', 'lat', 'lon', 'user', 'uid', 'version', 'changeset', 'timestamp']
NODE_TAGS_FIELDS = ['id', 'key', 'value', 'type']
WAY_FIELDS = ['id', 'user', 'uid', 'version', 'changeset', 'timestamp']
WAY_TAGS_FIELDS = ['id', 'key', 'value', 'type']
WAY_NODES_FIELDS = ['id', 'node_id', 'position']


def shape_element(element, node_attr_fields=NODE_FIELDS, way_attr_fields=WAY_FIELDS,
                  problem_chars=PROBLEMCHARS, default_tag_type='regular'):
    """Clean and shape node or way XML element to Python dict"""

    node_attribs = {}
    way_attribs = {}
    way_nodes = []
    tags = []  # Handle secondary tags the same way for both node and way elements
    secondary = {}
    nd = {}

    if element.tag == 'node':
        for i in NODE_FIELDS:
            node_attribs[i] = element.attrib[i]
            
        for child in element:
            if child.tag == "tag":
                v = child.attrib['v']
                k = child.attrib['k']
                if PROBLEMCHARS.search(k):
                    pass
                elif LOWER_COLON.search(k):
                    splitted = k.split(":", 1)
                    secondary['id'] = element.attrib['id']
                    secondary['key'] = splitted[1]
                    if splitted[1] == 'street': #fix street names
                        if v in faulty_name['Ave']:
                            new_v = update_name(v, mapping)
                            secondary['value'] = new_v
                        elif v in faulty_name['St.']:
                            new_v = update_name(v, mapping)
                            secondary['value'] = new_v
                        else:
                            secondary['value'] = v
                    elif splitted[1] == 'postcode': #fix postcode
                        new_postcode = update_postcode(v)
                        secondary['value'] = new_postcode
                    elif splitted[1] == 'province': #standardize province
                        if v == 'British Columbia':
                            standard_province = 'BC'
                            secondary['value'] = standard_province
                        else:
                            secondary['value'] = v
                    else:
                        secondary['value'] = v
                    secondary['type'] = splitted[0]
                else:
                    secondary['id'] = element.attrib['id']
                    secondary['key'] = k
                    secondary['value'] = v
                    secondary['type'] = 'regular'
                tags.append(secondary.copy())
        return {'node': node_attribs, 'node_tags': tags}

    elif element.tag == 'way':
        for i in WAY_FIELDS:
            way_attribs[i] = element.attrib[i]

        p = 0 #for position number in ways_nodes
        for child in element:
            if child.tag == "tag":
                v = child.attrib['v']
                k = child.attrib['k']
                if PROBLEMCHARS.search(k):
                    pass
                elif LOWER_COLON.search(k):
                    splitted = k.split(":", 1)
                    secondary['id'] = element.attrib['id']
                    secondary['key'] = splitted[1]
                    if splitted[1] == 'street': #fix street names
                        if v in faulty_name['Ave']:
                            new_v = update_name(v, mapping)
                            secondary['value'] = new_v
                        elif v in faulty_name['St.']:
                            new_v = update_name(v, mapping)
                            secondary['value'] = new_v
                        else:
                            secondary['value'] = v
                    elif splitted[1] == 'postcode': #fix postcode
                        new_postcode = update_postcode(v)
                        secondary['value'] = new_postcode
                    elif splitted[1] == 'province': #standardize province
                        if v == 'British Columbia':
                            standard_province = 'BC'
                            secondary['value'] = standard_province
                        else:
                            secondary['value'] = v
                    else:
                        secondary['value'] = v
                    secondary['type'] = splitted[0]
                else:
                    secondary['id'] = element.attrib['id']
                    secondary['key'] = k
                    secondary['value'] = v
                    secondary['type'] = 'regular'
                tags.append(secondary.copy())
            elif child.tag == "nd":
                nd['id'] = element.attrib['id']
                nd['node_id'] = child.attrib['ref']
                nd['position'] = p
                p += 1
                way_nodes.append(nd.copy())
        return {'way': way_attribs, 'way_nodes': way_nodes, 'way_tags': tags}


# ================================================== #
#               Helper Functions                     #
# ================================================== #
def get_element(osm_file, tags=('node', 'way', 'relation')):
    """Yield element if it is the right type of tag"""

    context = ET.iterparse(osm_file, events=('start', 'end'))
    _, root = next(context)
    for event, elem in context:
        if event == 'end' and elem.tag in tags:
            yield elem
            root.clear()


def validate_element(element, validator, schema=SCHEMA):
    """Raise ValidationError if element does not match schema"""
    if validator.validate(element, schema) is not True:
        field, errors = next(validator.errors.iteritems())
        message_string = "\nElement of type '{0}' has the following errors:\n{1}"
        error_strings = (
            "{0}: {1}".format(k, v if isinstance(v, str) else ", ".join(v))
            for k, v in errors.iteritems()
        )
        raise cerberus.ValidationError(
            message_string.format(field, "\n".join(error_strings))
        )


class UnicodeDictWriter(csv.DictWriter, object):
    """Extend csv.DictWriter to handle Unicode input"""

    def writerow(self, row):
        super(UnicodeDictWriter, self).writerow({
            k: (v.encode('utf-8') if isinstance(v, unicode) else v) for k, v in row.iteritems()
        })

    def writerows(self, rows):
        for row in rows:
            self.writerow(row)

def update_name(name, mapping): #used for fixing abbreviated street names
    word = name.split()[-1]
    for i in mapping:
        if word == i:
            new_name = name.rsplit(' ',1)[0] +' '+ mapping[i]
    return new_name

def update_postcode(postcode): #used for fixing postal codes
    if len(postcode) == 6:
        new_postcode = postcode[:3] + ' ' + postcode[3:]
    else:
        new_postcode = postcode
    return new_postcode

# ================================================== #
#               Main Function                        #
# ================================================== #
def process_map(file_in, validate):
    """Iteratively process each XML element and write to csv(s)"""

    with codecs.open(NODES_PATH, 'wb') as nodes_file,          codecs.open(NODE_TAGS_PATH, 'wb') as nodes_tags_file,          codecs.open(WAYS_PATH, 'wb') as ways_file,          codecs.open(WAY_NODES_PATH, 'wb') as way_nodes_file,          codecs.open(WAY_TAGS_PATH, 'wb') as way_tags_file:

        nodes_writer = UnicodeDictWriter(nodes_file, NODE_FIELDS)
        node_tags_writer = UnicodeDictWriter(nodes_tags_file, NODE_TAGS_FIELDS)
        ways_writer = UnicodeDictWriter(ways_file, WAY_FIELDS)
        way_nodes_writer = UnicodeDictWriter(way_nodes_file, WAY_NODES_FIELDS)
        way_tags_writer = UnicodeDictWriter(way_tags_file, WAY_TAGS_FIELDS)

        nodes_writer.writeheader()
        node_tags_writer.writeheader()
        ways_writer.writeheader()
        way_nodes_writer.writeheader()
        way_tags_writer.writeheader()

        validator = cerberus.Validator()

        for element in get_element(file_in, tags=('node', 'way')):
            el = shape_element(element)
            if el:
                if validate is True:
                    validate_element(el, validator)

                if element.tag == 'node':
                    nodes_writer.writerow(el['node'])
                    node_tags_writer.writerows(el['node_tags'])
                elif element.tag == 'way':
                    ways_writer.writerow(el['way'])
                    way_nodes_writer.writerows(el['way_nodes'])
                    way_tags_writer.writerows(el['way_tags'])


# In[ ]:

process_map('coquitlam.osm', validate=False)


# In[ ]:



