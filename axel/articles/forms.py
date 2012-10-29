"""Forms for the articles application"""
from django import forms
from haystack import connections
from axel.articles.utils import nlp

import tempfile
from axel.articles.utils.nlp import Stemmer


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

    article_pdf = forms.FileField(label="Article PDF")
    stem_func = forms.ChoiceField(choices=STEM_CHOICES, label="Stemming function")

    def get_collocations(self):
        """Extract collocations using the self.cleaned_data dictionary"""
        full_name = handle_uploaded_file(self.cleaned_data['article_pdf'])
        stem_func = getattr(Stemmer, self.cleaned_data['stem_func'])
        with open(full_name) as pdf_obj:
            extracted_data = connections['default'].get_backend().extract_file_contents(pdf_obj)
        full_text = nlp.stem_text(extracted_data['contents'], stem_func=stem_func)['text']
        collocs = nlp.collocations(full_text)
        # order colocations
        collocs.sort(key=lambda col: col[0], reverse=True)
        return collocs
