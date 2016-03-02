# These specs serve two purposes:
#     1: Provide a way to easily re-insert pages into binder sleeves,
#     2: Allow automated deletion of scanned pdfs,
#
# Specification:
#     Each binder sleeve is represented as X;Y
# where each of X Y is either a sequence abc, or empty
# where each of a,b,c is either a page:
#         0: an empty page, 
#         f: front of a page, 
#         b: back of a page,
#     a sheet (2 pages):
#         s: (=f0) a single-sided sheet,
#         d: (=fb) a double-sided page,
#     or multiple pages:
#         m: a multi-page document,
#     or an annotation: 
#         t: a tag stuck on the sleeve,
#
#     The whole binder is a sequence of binder sleeves
#         X1;Y1
#         X2;Y2
#         ...
#         Xn;Yn
#     with the joined string partitioned as documents by using {}, i.e. for example:
#         {X1;Y1
#         X2;}{Y2
#         ...
#         Xn;}{Yn}
#     Each document can further include subdocuments. E.g.
#         {X1;{Y1}
#         X2;}{Y2
#         ...
#         Xn;}{Yn}
#     IMPORTANT: For now these brackets will simply be ignored, and only the top-level syntax described below will be parsed
#
# Grammar:
#     - f and b must pair up correctly \todo{devise checks}
#     - t must be the first items in X and/or Y in a sleeve X;Y
#
# It is assumed that multi-page documents (m) will be removed and scanned separately. 
#
# Document short-hands:
#     Top-level documents can be partitioned by a clearer syntax using ---<<title>>---
#
# Sleeve short-hands: 
#     see dictionary short_hands below; they must occupy the entire line to be parsed
# 

short_hands = {
    '1': 'f;b',
    '2': 's;s',
    'sm': 's;m',
    'ms': 'm;s',
    't2': 'ts;s',
    '2t': 's;ts',
    't2t': 'ts;ts',
    't1': 'tf;b',
    '1t': 'f;tb',
    't1t': 'tf;tb',
    'tsm': 'ts;m',
    'smt': 's;tm',
    'tsmt': 'ts;tm',
    'tms': 'tm;s',
    'mst': 'm;ts',
    'tmst': 'tm;ts'
    }
DOC_DELIM = '&' #[hack] must be one character right now because of the assertion in char_func

import sys
import subprocess
#from os.path import splitext 
import re
from pprint import pprint
from argparse import ArgumentParser


def expand_short_hands(s):
	if s in short_hands.keys(): return short_hands[s]
	else: return s

def char_func(s):
	result = s.replace('{','').replace('}','').replace('m','').replace('t','').replace('s','f0').replace('d','fb').replace('f','1').replace('b','1')
	assert all(c in ['0', '1', DOC_DELIM] for c in result)
	return result

def split_into_docs(s):
	documents = re.split(r'---([\w\W]+?)---\n?', s)[1:] #[hack] remove the empty string in front
	titles, content = documents[0::2], documents[1::2]
	if DEBUG: print titles, content
	# [hack] sew the contents back together with a delimiter to parse front and back of sleeve, and then re-split using delimiter
	assert all(re.match(r'\A[\w\W]+\Z', s) for s in titles)
	# split into sleeves
	sleeves = [tuple(line.split(';')) for line in DOC_DELIM.join(['']+content).split('\n')]
	# for front page, do nothing; for back page, split around DOC_DELIM and reverse
	def reverse_if_not_DELIM(s):
		if s == DOC_DELIM: return s
		else: return s[::-1]
	if DEBUG: print sleeves
	content_char = ''.join([char_func(front_page) + DOC_DELIM.join(map(reverse_if_not_DELIM, char_func(back_page).split(DOC_DELIM))) for front_page, back_page in sleeves]).split(DOC_DELIM)[1:] #[make sure] apply char_func before reversing
	return zip(titles, content_char)

def find(s, ch):
    return [i for i, ltr in enumerate(s) if ltr == ch]

if __name__ == '__main__':
	parser = ArgumentParser()
	parser.add_argument('pdf_file', help="name of the pdf file")
	parser.add_argument('specfile', help="name of the .spec file")
	parser.add_argument("-n", "--dry-run", help="dry run; no pdf generated", action="store_true")
	parser.add_argument("-d", "--debug", help="output debugging logs", action="store_true")
	parser.add_argument("-v", "--verbose", help="more output", action="store_true")
	args = parser.parse_args()

	DEBUG = args.debug
	VERBOSE = args.verbose

	pdf_filename = args.pdf_file
	spec_filename = args.specfile
	with open(spec_filename, 'r') as specfile:
		spec = specfile.read()
	#pdf_reader = pyPdf.PdfFileReader(open(pdf_filename))

	# remove comments
	spec = re.sub(r'#\{.*?\}', '', spec)

	# expand short-hands
	spec = '\n'.join(map(expand_short_hands, spec.split('\n')))

	# split into documents
	docs = split_into_docs(spec)

	# for each doc, calculate page numbers (in the full pdf) of pages to export, stitching together docs with the same title
	pages_to_export = {}
	offset = 0
	for title, content_char in docs:
		if title not in pages_to_export:
			pages_to_export[title] = []
		pages_to_export[title].extend([offset+int(i)+1 for i in find(content_char, '1')])
		offset = offset + len(content_char)

	# assert number of pages match pdf
	titles, content_char = tuple(map(list,zip(*docs)))
	#assert len(''.join(content_char)) == pdf_reader.getNumPages()

	if DEBUG:
		print titles
		print content_char
		print "The original pdf is expected to have %s pages." % len(''.join(content_char))
		pprint(pages_to_export)

	def file_name(title):
		return title + '.pdf'
	def temp_file_name(title):
		return '.' + file_name(title)

	pdftk_error = False
	successful_titles = []
	if not args.dry_run:
		for title, page_numbers in pages_to_export.items():
			if not page_numbers:
				# handle titles with no content
				# [note] if directly passed to pdftk the entire raw pdf will be outputed
				if VERBOSE: print "...skipping %s. No content to export." % title
				continue
			if VERBOSE: print "...creating %s" % file_name(title)
			process = subprocess.Popen(['pdftk', pdf_filename, 'cat'] + map(str, page_numbers) + ['output', temp_file_name(title)], stderr=subprocess.PIPE)
			process.wait()
			error_msg = process.stderr.read()
			if error_msg != '':
				# if error for file
				print error_msg
				pdftk_error = True
				break
			else:
				# if no error for file
				successful_titles.append(title)
		if pdftk_error:
			# remove temp files
			for file_name in successful_titles:
				subprocess.call(['rm', '-f', file_name])
		else:
			# rename temp files to real files
			for title in successful_titles:
				subprocess.call(['mv', temp_file_name(title), file_name(title)])

	else:
		# dry run

		print "The following pdfs would be generated:"
		for title, pages in pages_to_export.items():
			print "\t%s.pdf\t%s pages" % (title, len(pages))
		print "for a total of %s pages." % sum(map(len, pages_to_export.values()))
