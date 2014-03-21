"""Forms for the articles application"""
from collections import defaultdict
import os
import subprocess
import tempfile
import networkx as nx
import pickle

from django import forms
from axel.articles.management.commands.ml_classify import RULES_DICT_START, RULES_DICT_END

from axel.libs import nlp
from axel.libs.nlp import Stemmer
from axel.libs.parse_pdfx_xml import parse_pdfx_xml


def handle_uploaded_file(f):
    """
    Put uploaded file to the tmp folder
    :returns: full saved file path
    """
    temp_name = tempfile.gettempdir() + f.name
    with open(temp_name, 'wb+') as destination:
        for chunk in f.chunks():
            destination.write(chunk)
    return temp_name


class PDFUploadForm(forms.Form):
    """Handle uploaded PDF and extract co-locations"""

    STEM_CHOICES = Stemmer.get_method_names()
    CLF = pickle.load(open('ngram_clf.pcl'))

    article_pdf = forms.FileField(label="Article PDF")
    stem_func = forms.ChoiceField(choices=STEM_CHOICES, label="Stemming function")

    def get_collocations(self):
        """Extract collocations using the self.cleaned_data dictionary"""
        full_name = handle_uploaded_file(self.cleaned_data['article_pdf'])
        stem_func = getattr(Stemmer, self.cleaned_data['stem_func'])

        if not os.path.exists(full_name + "x.xml"):
            subprocess.call(["/Users/dragoon/Libraries/pdfx/pdfx", full_name])
        extracted_data = parse_pdfx_xml(full_name + "x.xml")

        full_text = nlp.get_full_text(extracted_data)['text']
        article = PDFUploadForm.generate_temp_article(full_text)
        labels = []
        try:
            features = PDFUploadForm.build_features(article)
            for ngram, feature in features:
                klass = self.CLF.predict(feature)[0]
                labels.append((ngram, klass))
        finally:
            article.delete()
        return labels

    @staticmethod
    def build_features(article):
        from axel.stats.scores import compress_pos_tag

        component_size_dict = defaultdict(lambda: 0)
        dbpedia_graph = article.dbpedia_graph(redirects=True)
        dblp_component_set = set()
        for component in nx.connected_components(dbpedia_graph):
            nodes = [node for node in component if 'Category' not in node]
            stats_ngrams = article.CollocationModel.COLLECTION_MODEL.objects.filter(ngram__in=nodes)
            is_dblp_inside = bool([True for ngram in stats_ngrams if 'dblp' in ngram.source])
            if is_dblp_inside:
                dblp_component_set.update(nodes)
            comp_len = len(nodes)
            for node in component:
                component_size_dict[node] = comp_len

        features = []
        for colloc in article.CollocationModel.objects.filter(article=article):
            max_pos_tag = colloc.max_pos_tag
            collection_ngram = colloc.COLLECTION_MODEL.objects.get(ngram=colloc.ngram)
            pos_tag_start = str(compress_pos_tag(max_pos_tag, RULES_DICT_START))
            pos_tag_end = str(compress_pos_tag(max_pos_tag, RULES_DICT_END))
            feature = [
                int('NN_STARTS' == pos_tag_start),
                'dblp' in collection_ngram.source,
                int(colloc.ngram in dblp_component_set),
                component_size_dict[colloc.ngram],
                int('NN_ENDS' == pos_tag_end),
                int('VB_ENDS' == pos_tag_end),
                int('JJ_STARTS' == pos_tag_start),
            ]
            features.append((colloc.ngram, feature))
        return features

    @staticmethod
    def generate_temp_article(text):
        # TODO: make this Article class method
        from axel.articles.models import Article, Venue, TestCollocations
        import json
        venue = Venue.objects.get(acronym='SIGIR')
        stemmed_text = nlp.Stemmer.stem_wordnet(text)
        index = json.dumps(nlp.build_ngram_index(stemmed_text))
        article = Article(text=text, cluster_id='CS_COLLOCS', venue=venue, year=2013,
                          stemmed_text=stemmed_text, index=index)
        # TODO: extract title and abstract
        article.save_base(raw=True)
        article._create_collocations(True)
        for test_colloc in TestCollocations.objects.filter(article=article):
            obj = article.CollocationModel(ngram=test_colloc.ngram, count=test_colloc.count,
                                           article=article, total_count=0, extra_fields={})
            obj.save()
        TestCollocations.objects.filter(article=article).delete()
        return article


class ConceptAutocompleteForm(forms.Form):
    """Provide concept autocomplete field"""
    query = forms.CharField(widget=forms.TextInput(attrs={'class': 'input-xlarge search-query',
                                                          'autocomplete': 'off'}))
