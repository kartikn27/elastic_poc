from django.shortcuts import render
from django.conf import settings
from rest_framework.decorators import api_view
from django.views.decorators.csrf import csrf_protect
from elasticsearch_dsl.connections import connections
from elasticsearch import Elasticsearch
from elasticsearch_dsl import Search
from elasticsearch_dsl import Q
import json
from django import template
from random import randint
import re
import itertools
import unicodedata

register = template.Library()

# Create your views here.

client = Elasticsearch([settings.ELASTIC_HOST])

@api_view(['GET'])
def index(request):
	return render(request, 'index.html')


@api_view(['POST'])
def get_search(request):
	print(' request .. ', request.POST)
	restrictive = True
	check_keywords_in_description = True
	check_keywords_in_bio = True
	not_current_position = False
	if '0' in request.POST.get('restrictive'):
		restrictive = False

	
	if not 'descCheckK' in request.POST:
		check_keywords_in_description = False
	if not 'bioCheckK' in request.POST:
		check_keywords_in_bio = False

	if 'notCurrentPosition' in request.POST:
		not_current_position = True


	request_obj = {
	'not_current_position': not_current_position,
	'check_keywords_in_description': check_keywords_in_description,
	'check_keywords_in_bio': check_keywords_in_bio,
	'year_recency': request.POST['yearRecency'],
	'restrictive': restrictive,
	'locations': request.POST.get('locationsInput'), 
	'companies': request.POST.get('companiesInput'), 
	'keywords': request.POST.get('keywordsInput'), 
	'titles': request.POST.get('titlesInput') }
	result = process_search_request(request_obj)

	return render(request, 'show.html', result)


def process_search_request(request_obj):
	print('REQUEST OBJJJ ... ', request_obj)
	companies = request_obj['companies'].replace('"','')
	titles = request_obj['titles'].replace('"','')
	keywords = request_obj['keywords'].replace('"','')	
	#locations = request_obj['locations'].replace('"','')
	locations = 'locations'

	if companies == '' and titles == '' and keywords == '':
		return make_default_request();
	else:
		restrictive = True
		if request_obj['restrictive'] == True:
			return make_restrictive_request(companies, titles, keywords, locations, request_obj)
		else:
			return make_non_restrictive_request(companies, titles, keywords, locations, request_obj)
	

def make_default_request():
	print('in deafult')
	s = Search(index=settings.ELASTIC_INDEX).using(client).query()
	print(s.to_dict())	
	return execute_es_request(s)

def make_non_restrictive_request(companies, titles, keywords, locations, request_obj):
	must_list = []
	# if (get_companies_query_string(companies) != None):
	# 	must_list.append(get_companies_query_string(companies))
	if companies != '':
		companies = get_refined_titles(companies.lower())
		should_list_companies = []
		for company in companies:
			should_list_companies.append(get_companies_match_phrase(company))
		must_list.append(Q('bool', should=should_list_companies))
	if (get_titles_query_string(titles) != None):
		must_list.append(get_titles_query_string(titles))
	# if (request_obj['check_keywords_in_description'] == True):
	# 	if (get_description_query_string(keywords) != None):
	# 		must_list.append(get_description_query_string(keywords))
	if (get_locations_query_string(locations) != None):
		must_list.append(get_locations_query_string(locations))
	# if (request_obj['check_keywords_in_bio'] == True):
	# 	if (get_bio_query_string(keywords) != None):
	# 		must_list.append(get_bio_query_string(keywords))

	if (request_obj['check_keywords_in_description'] == True) and (request_obj['check_keywords_in_bio'] == True):
		if (get_description_bio_query_string(keywords) != None):
			must_list.append(get_description_bio_query_string(keywords))
	elif (request_obj['check_keywords_in_description'] == True) and (request_obj['check_keywords_in_bio'] == False):
		if (get_description_query_string(keywords) != None):
			must_list.append(get_description_query_string(keywords))
	elif (request_obj['check_keywords_in_description'] == False) and (request_obj['check_keywords_in_bio'] == True):
		if (get_bio_query_string(keywords) != None):
			must_list.append(get_bio_query_string(keywords))

	if (request_obj['year_recency'] != ''):
		must_list.append(Q('range', positions__enddateyear={'gte': int(request_obj['year_recency'])}))

	if (request_obj['not_current_position'] == True):		
		must_list.append(Q('bool', must_not=Q('match', positions__position_type='Current')))


	q = Q('bool',
		must=must_list)
	
	s = Search(index=settings.ELASTIC_INDEX).using(client).query('nested', path="positions", query=q, inner_hits={"highlight": {
		  "pre_tags" : ["<strong>"],
		  "post_tags" : ["</strong>"],
          "fields": {
            "positions.companyname": {},
            "positions.description": {},
            "positions.title": {}
          }
        }})[0:100]	

	print(s.to_dict())	
	return execute_es_request(s)


def make_restrictive_request(companies, titles, keywords, locations, request_obj):
	must_list = []

	if companies != '':
		companies = get_refined_titles(companies.lower())
		should_list_companies = []
		for company in companies:
			should_list_companies.append(get_companies_match_phrase(company))
		must_list.append(Q('bool', should=should_list_companies))		

	if titles != '':
		titles = get_refined_titles(titles.lower())
		should_list_titles = []
		for title in titles:			
			should_list_titles.append(get_titles_match_phrase(title))
		must_list.append(Q('bool', should=should_list_titles))

	if (request_obj['check_keywords_in_description'] == True) and (request_obj['check_keywords_in_bio'] == True):
		if keywords != '':
			keywords_description_bio = get_refined_titles(keywords.lower())
			should_list_description_bio = []
			for keyword in keywords_description_bio:
				should_list_description_bio.append(get_description_match_phrase(keyword))
				should_list_description_bio.append(get_bio_match_phrase(keyword))
			must_list.append(Q('bool', should=should_list_description_bio))
	elif (request_obj['check_keywords_in_description'] == True) and (request_obj['check_keywords_in_bio'] == False):
		if keywords != '':
			keywords_description = get_refined_titles(keywords.lower())	
			should_list_description = []
			for keyword in keywords_description:
				should_list_description.append(get_description_match_phrase(keyword))
			must_list.append(Q('bool', should=should_list_description))
	elif (request_obj['check_keywords_in_description'] == False) and (request_obj['check_keywords_in_bio'] == True):
		if keywords != '':
			keywords_bio = get_refined_titles(keywords.lower())
			should_list_bio = []
			for keyword in keywords_bio:
				should_list_bio.append(get_bio_match_phrase(keyword))
			must_list.append(Q('bool', should=should_list_bio))

	# if (request_obj['check_keywords_in_description'] == True):
	# 	if keywords != '':
	# 		keywords_description = get_refined_titles(keywords.lower())	
	# 		should_list_description = []
	# 		for keyword in keywords_description:
	# 			should_list_description.append(get_description_match_phrase(keyword))
	# 		must_list.append(Q('bool', should=should_list_description))

	# if (request_obj['check_keywords_in_bio'] == True):
	# 	if keywords != '':
	# 		keywords_bio = get_refined_titles(keywords.lower())
	# 		should_list_bio = []
	# 		for keyword in keywords_bio:
	# 			should_list_bio.append(get_bio_match_phrase(keyword))
	# 		must_list.append(Q('bool', should=should_list_bio))

	if (request_obj['year_recency'] != ''):
		must_list.append(Q('range', positions__enddateyear={'gte': int(request_obj['year_recency'])}))

	if (request_obj['not_current_position'] == True):		
		must_list.append(Q('bool', must_not=Q('match', positions__position_type='Current')))

	#print(' must list .. ', must_list)
	
	q = Q('bool',
		must=must_list)

	s = Search(index=settings.ELASTIC_INDEX).using(client).query('nested', path="positions", query=q, inner_hits={"highlight": {
	  "pre_tags" : ["<strong>"],
	  "post_tags" : ["</strong>"],
      "fields": {
        "positions.companyname": {},
        "positions.description": {},
        "positions.title": {}
      }
    }})[0:100]

	print(s.to_dict())
	return execute_es_request(s)


def execute_es_request(es_request):
	search_result = es_request.execute()
	res = json.loads(json.dumps(search_result.to_dict()).replace('_source','source').
		replace('positions.description','description').
		replace('positions.companyname','companyname').
		replace('positions.title','title').
		replace('positions.startdatemonth','startdatemonth').
		replace('positions.position_type','position_type').
		replace('positions.startdateyear','startdateyear').
		replace('positions.companyurl','companyurl').
		replace('positions.enddatemonth','enddatemonth').
		replace('positions.enddateyear','enddateyear'))
	
	experts_list = []
	for hit in res['hits']['hits']:
		matches = []
		if 'inner_hits' in hit:
			for match in hit['inner_hits']['positions']['hits']['hits']:			
				if 'highlight' in match:
					matches.append({
					'id_random': str(randint(0, 999999999)),
					'title': ' '.join(match['highlight']['title'] if 'title' in match['highlight'] else ''),
					'companyname': '. '.join(match['highlight']['companyname'] if 'companyname' in match['highlight'] else 'N/A'),
					'description': '. '.join(match['highlight']['description']) if 'description' in match['highlight'] else 'No matching description'},
					)
				experts_list.append({ 'source': hit['source'], 'matches': matches })
	return {'count': search_result.hits.total, 'experts': experts_list}	
		


def get_bio_match_phrase(keyword):
	if keyword != '':
		return Q('match_phrase', positions__short_bio=keyword)
	else:
		return

def get_companies_match_phrase(company):
	if company != '':
		return Q('match_phrase', positions__companyname=company)
	else:
		return

def get_titles_match_phrase(title):
	if title != '':
		return Q('match_phrase', positions__title=title)
	else:
		return

def get_description_match_phrase(keyword):
	if keyword != '':
		return Q('match_phrase', positions__description=keyword)
	else:
		return

def get_bio_query_string(keywords):
	if keywords != '':
		return Q('query_string', default_field='short_bio', query=keywords)
	else:
		return

def get_companies_query_string(companies):
	if companies != '':
		return Q('query_string', default_field='positions.companyname', query=companies)
	else:
		return

def get_titles_query_string(titles):
	if titles != '':
		return Q('query_string', default_field='positions.title', query=titles)
	else:
		return	

def get_description_query_string(keywords):
	if keywords != '':
		return Q('query_string', default_field='positions.description', query=keywords)
	else:
		return

def get_description_bio_query_string(keywords):
	if keywords != '':
		return Q('query_string', fields=['positions.description', 'short_bio'], query=keywords)
	else:
		return	

def get_locations_query_string(locations):
	if locations != '':
		return Q('query_string', default_field='positions.lip_exact_entry', query=locations)
	else:
		return

def get_refined_titles(title):	
	title = re.sub('[^[\W_]-/.&\' ]+', '', title)
	title = title.replace('(', '').replace(')', '')
	title = strip_accents(title)
	titles = tsplit(title, (' or ', ' and '))	
	return titles

def strip_accents(value):
    return ''.join(char for char in
                   unicodedata.normalize('NFKD', value)
                   if unicodedata.category(char) != 'Mn')    

def tsplit(string, delimiters):
    """Behaves str.split but supports multiple delimiters."""
    delimiters = tuple(delimiters)
    stack = [string, ]

    for delimiter in delimiters:
        for i, substring in enumerate(stack):
            substack = substring.split(delimiter)
            stack.pop(i)
            for j, _substring in enumerate(substack):
                stack.insert(i + j, _substring)

    return stack    
