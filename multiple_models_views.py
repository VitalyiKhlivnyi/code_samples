from drf_multiple_model.views import FlatMultipleModelAPIView

from rest_framework.response import Response
from django.db.models.query import QuerySet
from django.db.models import Value, CharField


class FlatMultipleModelWithSortingAPIView(FlatMultipleModelAPIView):
    """
    At first step we create union for different models, so annotation, select/prefetch related sometimes causing
    unexpected errors. So we add them to querysets before getting objects for final sorting (3d step in list method)

    :ivar select_related_fields_per_model:
        description: dict, where key - is model name, value - is list of fields names for select
        related.
        format: {"ModelName1": ["field1", "field2", ...], "ModelName2": ["field3", "field4", ...], }

    :ivar prefetch_related_fields_per_model:
        description: dict, where key - is model name, value - is list of fields names for prefetch
        related.
        format: {"ModelName1": ["field1", "field2", ...], "ModelName2": ["field3", "field4", ...], }

    :ivar annotate_additional_fields_per_model:
        description: dict, where key - is model name, value - is dict of fields names (keys) and
        annotate expression (values).
        format: {"ModelName1": {"field1": annotate_expression1, "field2": annotate_expression2, ...},
                 "ModelName2": {"field3": annotate_expression3, "field4": annotate_expression4, ...}}

    You can rewrite this attributes or related methods:
        - select_related_fields_per_model - get_select_related_fields_per_model
        - annotate_additional_fields_per_model - get_annotate_additional_fields_per_model
        - prefetch_related_fields_per_model - get_prefetch_related_fields_per_model
    """
    select_related_fields_per_model = None  # in format {"model_label": ['select related fields list]}
    annotate_additional_fields_per_model = None  # in format {"model_label":{"annotate_field_name":annotate expression}}
    prefetch_related_fields_per_model = None  # in format {"model_label": ['prefetch related fields list]}

    def get_sorting_fields(self):
        if self.sorting_parameter_name in self.request.query_params:
            # Extract sorting parameter from query string
            sorting_fields = []
            for one_field in self.request.query_params.get(self.sorting_parameter_name).split(','):
                sorting_field = one_field.strip()
                if sorting_field.strip():
                    sorting_fields.append(sorting_field)

            return sorting_fields
        else:
            return self.sorting_fields

    def get_union_query_set(self, querylist, request, *args, **kwargs):
        union_queryset = None
        label_list = list()
        sorting_fields = self.get_sorting_fields()
        sorting_fields_names = [field.lstrip('-') for field in sorting_fields]
        for query_data in querylist:
            self.check_query_data(query_data)
            queryset = self.load_queryset(query_data, request, *args, **kwargs)
            label = self.get_label(queryset, query_data)
            label_list.append(label)
            queryset = queryset.only('id', *sorting_fields_names) \
                .annotate(class_name=Value(label, output_field=CharField()))
            if union_queryset:
                union_queryset = union_queryset.union(queryset)
            else:
                union_queryset = queryset
        union_queryset = union_queryset.order_by(*sorting_fields)
        return union_queryset, label_list

    def load_queryset(self, query_data, request, *args, **kwargs):
        """
        Fetches the queryset and runs any necessary filtering, both
        built-in rest_framework filters and custom filters passed into
        the querylist
        """
        queryset = query_data.get('queryset', [])
        id_list = kwargs.get('id_list')

        if isinstance(queryset, QuerySet):
            # Ensure queryset is re-evaluated on each request.
            queryset = queryset.all()

        # run rest_framework filters
        queryset = self.filter_queryset(queryset)

        # run custom filters
        filter_fn = query_data.get('filter_fn', None)
        if filter_fn is not None:
            queryset = filter_fn(queryset, request, *args, **kwargs)

        if id_list:
            queryset = queryset.filter(pk__in=id_list)
        return queryset

    @staticmethod
    def get_label_id_dict(object_list, label_list):
        label_id_dict = dict()
        for item in object_list:
            try:
                label_id_dict[item.class_name].append(item.id)
            except KeyError:
                label_id_dict[item.class_name] = list()
                label_id_dict[item.class_name].append(item.id)
        return label_id_dict

    def get_select_related_fields_per_model(self):
        return self.select_related_fields_per_model

    def get_annotate_additional_fields_per_model(self):
        return self.annotate_additional_fields_per_model

    def get_prefetch_related_fields_per_model(self):
        return self.prefetch_related_fields_per_model

    def list(self, request, *args, **kwargs):
        querylist = self.get_querylist()

        results = self.get_empty_results()

        """
        1) create union queryset with all required models (from querylist) with next fields:
            - id - object id
            - class_name - annotated class name
            - and all required for ordering fields
        """
        union_queryset, label_list = self.get_union_query_set(querylist, request, *args, **kwargs)

        """
        2) get required page from union queryset
        """
        page = self.paginate_queryset(union_queryset)
        self.is_paginated = page is not None

        full_id_list = self.get_label_id_dict(page, label_list)

        """
        3) get objects from every queryset in querylist filtered by id
        """
        for query_data in querylist:

            queryset = self.load_queryset(query_data, request, *args, **kwargs)

            label = self.get_label(queryset, query_data)

            id_list = full_id_list.get(label)
            if id_list:
                queryset = queryset.filter(id__in=id_list)
            else:
                continue

            # apply select related conditions to queryset, if needed
            select_related_fields_per_model = self.get_select_related_fields_per_model()
            if select_related_fields_per_model and select_related_fields_per_model.get(label):
                model_select_related_fields = select_related_fields_per_model.get(label)
                queryset = queryset.select_related(*model_select_related_fields)

            # apply annotate conditions to queryset, if needed
            annotate_additional_fields_per_model = self.get_annotate_additional_fields_per_model()
            if annotate_additional_fields_per_model and annotate_additional_fields_per_model.get(label):
                model_annotate_fields = annotate_additional_fields_per_model.get(label)
                queryset = queryset.annotate(**model_annotate_fields)

            # apply prefetch related conditions to queryset, if needed
            prefetch_related_fields_per_model = self.get_prefetch_related_fields_per_model()
            if prefetch_related_fields_per_model and prefetch_related_fields_per_model.get(label):
                model_prefetch_related_fields = prefetch_related_fields_per_model.get(label)
                queryset = queryset.prefetch_related(*model_prefetch_related_fields)

            # Run the paired serializer
            context = self.get_serializer_context()
            data = query_data['serializer_class'](queryset, many=True, context=context).data

            # Add the serializer data to the running results tally
            results = self.add_to_results(data, label, results)

        """
        4) final ordering with sorted function
        """
        formatted_results = self.format_results(results, request)

        if self.is_paginated:
            try:
                formatted_results = self.paginator.format_response(formatted_results)
            except AttributeError:
                raise NotImplementedError(
                    "{} cannot use the regular Rest Framework or Django paginators as is. "
                    "Use one of the included paginators from `drf_multiple_models.pagination "
                    "or subclass a paginator to add the `format_response` method."
                    "".format(self.__class__.__name__)
                )

        return Response(formatted_results)

    def prepare_sorting_fields(self):
        """
        Determine sorting direction and sorting field based on request query parameters and sorting options
        of self
        """
        if self.sorting_parameter_name in self.request.query_params:
            self._sorting_fields = []
            for one_field in self.request.query_params.get(self.sorting_parameter_name).split(','):
                sorting_field = one_field.strip()
                if sorting_field.strip():
                    self._sorting_fields.append(sorting_field)

        if self._sorting_fields:
            # Create a list of sorting parameters. Each parameter is a tuple: (field:str, descending:bool)
            self._sorting_fields = [
                (self.sorting_fields_map.get(field.lstrip('-'), field.lstrip('-')), field[0] == '-')
                for field in self._sorting_fields
            ]
