from google.appengine.ext import webapp
from google.appengine.ext.webapp.util import run_wsgi_app
from google.appengine.ext.webapp import template

from google.appengine.api import urlfetch

from django.utils import simplejson

from models import School

import re
import unicodedata
import os
import codecs
import logging
import string

def slugify(value):
    value = unicodedata.normalize('NFKD', value).encode('ascii', 'ignore')
    value = unicode(re.sub('[^\w\s-]', '', value).strip().lower())
    return re.sub('[-\s]+', '-', value)

# Views

class MainPage(webapp.RequestHandler):
    def get(self):        
        values = {}
        
        templatepath = os.path.join(os.path.dirname(__file__), 'templates', 'index.html')
        self.response.out.write(template.render(templatepath, values))


class DataPage(webapp.RequestHandler):
    def get(self):
        templatepath = os.path.join(os.path.dirname(__file__), 'templates', 'data.html')
        self.response.out.write(template.render(templatepath, {'q': ' '}))
        
        
class AboutPage(webapp.RequestHandler):
    def get(self):
        templatepath = os.path.join(os.path.dirname(__file__), 'templates', 'about.html')
        self.response.out.write(template.render(templatepath, {'q': ' '}))


class SchoolPage(webapp.RequestHandler):
    def get(self, brin, slug=''):
        format = self.request.get('format')
        
        schoolURL = 'http://www.cfi.nl/Public/BriWeb/detail.asp?brinnummer=%s' % brin
        logging.info('fetching %s', schoolURL)
        schoolResult = urlfetch.fetch(schoolURL)
        
        if schoolResult.status_code == 200:
            schoolData = {}
            
            def getTableValue(name, content):
                matches = re.search(name + '</th>\s+<td>(.+?)</td>', content, re.M)
                if matches:
                    value = matches.group(1)
                    logging.info('got value %s' % value)
                else:
                    value = ''
                return value
            
            schoolData['name'] = getTableValue('Naam', schoolResult.content)
            schoolData['telephone'] = getTableValue('Telefoon', schoolResult.content)
            schoolData['website'] = getTableValue('Website', schoolResult.content)
            schoolData['area'] = getTableValue('Onderwijsgebied', schoolResult.content)
            schoolData['kind'] = getTableValue('Soort', schoolResult.content)
            schoolData['street'] = getTableValue('Straat', schoolResult.content)
            schoolData['postcodecity'] = getTableValue('Postcode / Plaats', schoolResult.content)
            schoolData['muni'] = getTableValue('Gemeente', schoolResult.content)
            
            values = {'school': schoolData,
                        'url': schoolURL}

            # Fetch schoolpage from OIC
            
            if format == 'json':
                self.response.headers["Content-Type"] = "text/json"
                self.response.out.write(simplejson.dumps(values))
            else:
                templatepath = os.path.join(os.path.dirname(__file__), 'templates', 'school.html')
                self.response.out.write(template.render(templatepath, values))


class LoadSchools(webapp.RequestHandler):
    def get(self):
        self.response.out.write('processing data<br>')
        
        datapath = os.path.join(os.path.dirname(__file__), 'data.csv')
        
        logging.info(datapath)
        
        datafile = codecs.open(datapath, 'r', 'iso-8859-15')
        
        for line in datafile.readlines():
            parts = line.split(';')
            
            logging.debug(parts)
            
            school = School()
            school.brin = parts[0].strip()[1:-1]
            school.name = parts[1].strip()[1:-1]
            school.slug = slugify(school.name)
            
            school.put()
            
            logging.info('created school ' + str(school.key().id()))
            
            self.response.out.write('%s %s %s <br>' % (school.brin, school.name, school.slug))
        datafile.close()


class SearchResult(webapp.RequestHandler):
    def get(self):
        querystring = self.request.get('q').strip()
        
        filtercriterium = self.request.get('filter')
        
        filtermappings = {'lager': "BAS", 
                        'middelbaar': "VOS",
                        'vervolg': ''}
        
        onderwijssector = ''
        if filtercriterium:
            onderwijssector = filtermappings[filtercriterium] + '&ck_6=on'
        
        pageNumber = 0
        if self.request.get('page'):
            try:
                pageNumber = int(self.request.get('page'))
            except:
                pass # pagenumber stays 0
                
        logging.info('page number %d', pageNumber)
        
        # Very odd XML output result
        # http://www.cfi.nl/Public/BriWeb/raadplegen.asp?actie=raadplegen&page=0&download=xml
        
        csvUrl = ''
        if len([l for l in querystring if l in string.digits]) > 2:
            postcode = int(''.join([l for l in querystring if l in string.digits]))
            
            logging.info('looking for postal code %d', postcode)
            
            upperBound = postcode+10
            lowerBound = postcode-10
            
            csvUrl = 'http://www.cfi.nl/Public/BriWeb/raadplegen.asp?actie=raadplegen&nav=1&postcode=%dAA&postcode2=%dZZ&onderwijsgebied=0&onderwijssector=%s&ck_3=on&ck_8=on&page=0&download=csv' % (lowerBound, upperBound, onderwijssector)
        else:
            encodedQuery = querystring.replace(' ', '+')
            csvUrl = 'http://www.cfi.nl/Public/BriWeb/raadplegen.asp?actie=raadplegen&nav=1&plaatsnaam=%s&onderwijsgebied=0&onderwijssector=%s&ck_4=on&ck_8=on&page=0&download=csv' % (encodedQuery, onderwijssector)
        
        logging.info('url to fetch %s', csvUrl)
        
        searchResult = urlfetch.fetch(csvUrl)
        result = []
        
        # TODO do something if the resultset is empty
        
        if searchResult.status_code == 200:
            for line in searchResult.content.split('\n'):
                if ';' in line:
                    brin = line.split(';')[0].strip()[1:-1]
                    name = line.split(';')[1].strip()[1:-1]
                    slug = slugify(unicode(name, 'iso-8859-15'))
                    
                    result.append((brin, name, slug))
                    
        # Page the resultset we just got
        pageCount = 10
        
        if len(result) > (pageNumber+1)*pageCount:
            nextPage = True
        else:
            nextPage = False

        if pageNumber == 0:
            previousPage = False
        else:
            previousPage = True
        
        if pageNumber * pageCount > len(result):
            result = result[:-10] # get the last 10
            # TODO also adjust the pageNumber
        else:
            result = result[pageNumber*pageCount:(pageNumber+1)*pageCount]
                
        values = {'q': querystring,
                'filter': filtercriterium,
                'results': result,
                'size': len(result),
                'csv': csvUrl,
                'page': pageNumber,
                'nextPage': nextPage,
                'previousPage': previousPage}
        
        templatepath = os.path.join(os.path.dirname(__file__), 'templates', 'index.html')
        self.response.out.write(template.render(templatepath, values))

# URL routing

application = webapp.WSGIApplication(
                         [('/', MainPage),
                          ('/school/([^/]+?)/([^/]+?)/', SchoolPage),
                          ('/school/([^/]+?)/', SchoolPage),
                          ('/search/', SearchResult),
                          ('/load/', LoadSchools),
                          ('/data/', DataPage),
                          ('/over/', AboutPage)],
                         debug=True)

def main():
    run_wsgi_app(application)

if __name__ == "__main__":
    main()