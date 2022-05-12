import logging
import json
from ontobio.sparql.sparql_ontol_utils import run_sparql_on, EOntology, transform, transformArray
from ontobio.golr.golr_query import run_solr_on, replace
from ontobio.io.ontol_renderers import OboJsonGraphRenderer
from ..utils.ontology.ontology_manager import get_ontology

from typing import List
from fastapi import APIRouter, Query
from .slimmer import gene_to_uniprot_from_mygene
from ontobio.util.user_agent import get_user_agent
from ontobio.golr.golr_query import run_solr_text_on, ESOLR, ESOLRDoc

log = logging.getLogger(__name__)

USER_AGENT = get_user_agent(name="go-fastapi", version="0.1.0")
router = APIRouter()

# Some query parameters & parsers
IS_A = "isa"
IS_A_PART_OF = "isa_partof"
REGULATES = "regulates"
TOPOLOGY = "topology_graph"
REGULATES_TRANSITIVITY = "regulates_transitivity_graph"
NEIGHBORHOOD_GRAPH = "neighborhood_graph"
NEIGHBORHOOD_LIMITED_GRAPH = "neighborhood_limited_graph"

aspect_map = {
    "P": "GO:0008150",
    "F": "GO:0003674",
    "C": "GO:0005575"
}

# related_params.add_argument('relationship_type', choices=[IS_A, IS_A_PART_OF, REGULATES], default=IS_A_PART_OF,
#                            help="relationship type ('{}', '{}' or '{}')".format(IS_A, IS_A_PART_OF, REGULATES))

#graph_params.add_argument('graph_type',
#                          choices=[TOPOLOGY, REGULATES_TRANSITIVITY, NEIGHBORHOOD_GRAPH, NEIGHBORHOOD_LIMITED_GRAPH],
#                          default=TOPOLOGY,
#                          help="graph type ('{}', '{}' or '{}')".format(TOPOLOGY, REGULATES_TRANSITIVITY,
#                                                                        NEIGHBORHOOD_GRAPH))


@router.post("/ontology/term/{id}", tags=["ontology"])
async def get_term_metadata_by_id(id: str,
                                  relationship_type: str = Query(None, include_in_schema=False),
                                  graph_type: str = Query(None, include_in_schema=False),
                                  cnode: str = Query(None, include_in_schema=False),
                                  include_ancestors: bool = Query(True, include_in_schema=False),
                                  include_descendents: bool = Query(True, include_in_schema=False),
                                  relation:  List[str] = Query(['subClassOf', 'BFO:0000050'], include_in_schema=False),
                                  include_meta: bool = Query(False, include_in_schema=False)):
    """
    Returns meta data of an ontology term, e.g. GO:0003677
    """
    query = go_summary(id)
    results = run_sparql_on(query, EOntology.GO)
    return transform(results[0], ['synonyms', 'relatedSynonyms', 'alternativeIds', 'xrefs', 'subsets'])


@router.post("/ontology/term/{id}/graph", tags=["ontology"])
async def get_term_graph_by_id(id: str, graph_type: str = Query(None),
                               relationship_type: str = Query(None, include_in_schema=False),
                               cnode: str = Query(None, include_in_schema=False),
                               include_ancestors: bool = Query(True, include_in_schema=False),
                               include_descendents: bool = Query(True, include_in_schema=False),
                               relation: List[str] = Query(['subClassOf', 'BFO:0000050'], include_in_schema=False),
                               include_meta: bool = Query(False, include_in_schema=False)
                               ):
        """
        Returns graph of an ontology term
        """

        graph_type = graph_type + "_json"  # GOLR field names

        data = run_solr_on(ESOLR.GOLR, ESOLRDoc.ONTOLOGY, id, graph_type)
        # step required as these graphs are stringified in the json
        data[graph_type] = json.loads(data[graph_type])

        return data


@router.post("/ontology/term/{id}/subgraph", tags=["ontology"])
async def get_subgraph_by_term_id(id: str, graph_type: str = Query(None),
                               relationship_type: str = Query(None, include_in_schema=False),
                               cnode: str = Query(None, include_in_schema=False),
                               include_ancestors: bool = Query(True, include_in_schema=False),
                               include_descendants: bool = Query(True, include_in_schema=False),
                               relation: List[str] = Query(['subClassOf', 'BFO:0000050'], include_in_schema=False),
                               include_meta: bool = Query(False, include_in_schema=False)
                               ):
        """
        Extract a subgraph from an ontology term
        """
        qnodes = [id]
        if cnode is not None:
            qnodes += cnode

        # COMMENT: based on the CURIE of the id, we should be able to find out the ontology automatically
        ont = get_ontology("go")
        relations = relation
        print("Traversing: {} using {}".format(qnodes, relations))
        nodes = ont.traverse_nodes(qnodes,
                                   up=include_ancestors,
                                   down=include_descendants,
                                   relations=relations)

        subont = ont.subontology(nodes, relations=relations)
        # TODO: meta is included regardless of whether include_meta is True or False
        ojr = OboJsonGraphRenderer(include_meta=include_meta)
        json_obj = ojr.to_json(subont, include_meta=include_meta)
        return json_obj

@router.post("/ontology/term/{id}/subsets", tags=["ontology"])
async def get_subset_by_term(id: str):

        """
        Returns subsets (slims) associated to an ontology term
        """
        query = get_go_subsets(id)
        results = run_sparql_on(query, EOntology.GO)
        results = transformArray(results, [])
        results = replace(results, "subset", "OBO:go#", "")
        return results


@router.post("/ontology/term/{id}", tags=["ontology"])
async def get_subset_metadata_by_id(id: str):
        """
        Returns meta data of an ontology subset (slim)
        id is the name of a slim subset, e.g., goslim_agr, goslim_generic
        """

        q = "*:*"
        qf = ""
        fq = "&fq=subset:" + id + "&rows=1000"
        fields = "annotation_class,annotation_class_label,description,source"

        # This is a temporary fix while waiting for the PR of the AGR slim on go-ontology
        if id == "goslim_agr":

            terms_list = set()
            for section in agr_slim_order:
                terms_list.add(section['category'])
                for term in section['terms']:
                    terms_list.add(term)

            goslim_agr_ids = "\" \"".join(terms_list)
            fq = "&fq=annotation_class:(\"" + goslim_agr_ids + "\")&rows=1000"

        data = run_solr_text_on(ESOLR.GOLR, ESOLRDoc.ONTOLOGY, q, qf, fields, fq)

        tr = {}
        for term in data:
            source = term['source']
            if source not in tr:
                tr[source] = {"annotation_class_label": source, "terms": []}
            ready_term = term.copy()
            del ready_term["source"]
            tr[source]["terms"].append(ready_term)

        cats = []
        for category in tr:
            cats.append(category)

        fq = "&fq=annotation_class_label:(" + " or ".join(cats) + ")&rows=1000"
        data = run_solr_text_on(ESOLR.GOLR, ESOLRDoc.ONTOLOGY, q, qf, fields, fq)

        for category in tr:
            for temp in data:
                if temp["annotation_class_label"] == category:
                    tr[category]["annotation_class"] = temp["annotation_class"]
                    tr[category]["description"] = temp["description"]
                    break

        result = []
        for category in tr:
            cat = tr[category]
            result.append(cat)

            # if goslim_agr, reorder the list based on the temporary json object below
        if id == "goslim_agr":
            temp = []
            for agr_category in agr_slim_order:
                cat = agr_category['category']
                for category in result:
                    if category['annotation_class'] == cat:
                        ordered_terms = []
                        for ot in agr_category['terms']:
                            for uot in category['terms']:
                                if uot['annotation_class'] == ot:
                                    ordered_terms.append(uot)
                                    break
                        category["terms"] = ordered_terms
                        temp.append(category)
            result = temp

        return result


@router.post("/ontology/shared/{subject}/{object}", tags=["ontology"])
async def get_subset_metadata_by_id(subject: str, object: str):
        """
        Returns the ancestor ontology terms shared by two ontology terms

        subject: 'CURIE identifier of a GO term, e.g. GO:0006259'
        object: 'CURIE identifier of a GO term, e.g. GO:0046483'
        """

        fields = "isa_partof_closure,isa_partof_closure_label"

        subres = run_solr_on(ESOLR.GOLR, ESOLRDoc.ONTOLOGY, subject, fields)
        objres = run_solr_on(ESOLR.GOLR, ESOLRDoc.ONTOLOGY, object, fields)

        print("SUBJECT: ", subres)
        print("OBJECT: ", objres)

        shared = []
        shared_labels = []
        for i in range(0, len(subres['isa_partof_closure'])):
            sub = subres['isa_partof_closure'][i]
            found = False
            if sub in objres['isa_partof_closure']:
                found = True
            if found:
                shared.append(sub)
                shared_labels.append(subres['isa_partof_closure_label'][i])
        return {"goids": shared, "gonames: ": shared_labels}


def get_category_terms(category):
    terms = []
    for group in category["groups"]:
        if group["type"] == "Term":
            terms.append(group)
    return terms


@router.post("/ontology/ribbon/", tags=["ontology"])
async def get_subset_metadata_by_id(subset: str,
                                    subject: List[str] = Query(None),
                                    ecodes: List[str] = Query(None),
                                    exclude_IBA: bool = False,
                                    exclude_PB: bool = False,
                                    cross_aspect: bool = False):

    """
    Fetch the summary of annotations for a given gene or set of genes

    :param subset: Name of the subset to map GO terms (e.g. goslim_agr)
    :param subject: List of Gene ids (e.g. MGI:98214, RGD:620474)
    :param ecodes: List of Evidence Codes to include (e.g. EXP, IDA). Has priority over exclude_IBA
    :param exclude_IBA: If true, excludes IBA annotations
    :param exclude_PB: If true, excludes direct annotations to protein binding
    :param cross_aspect: If true, can retrieve terms from other aspects if using a cross-aspect relationship such as regulates_closure

    :return:
    """


    # Step 1: create the categories
    categories = await get_subset_metadata_by_id(subset)
    for category in categories:

        category["groups"] = category["terms"]
        del category["terms"]

        category["id"] = category["annotation_class"]
        del category["annotation_class"]

        category["label"] = category["annotation_class_label"]
        del category["annotation_class_label"]

        for group in category["groups"]:
            group["id"] = group["annotation_class"]
            del group["annotation_class"]

            group["label"] = group["annotation_class_label"]
            del group["annotation_class_label"]

            group["type"] = "Term"

        category["groups"] = [{"id": category["id"],
                               "label": "all " + category["label"].lower().replace("_", " "),
                               "description": "Show all " + category["label"].lower().replace("_",
                                                                                              " ") + " annotations",
                               "type": "All"}] + category["groups"] + [{"id": category["id"],
                                                                        "label": "other " + category[
                                                                            "label"].lower().replace("_", " "),
                                                                        "description": "Represent all annotations not "
                                                                                       "mapped to a specific term",
                                                                        "type": "Other"}]

    # Step 2: create the entities / subjects
    subject_ids = subject

    # ID conversion
    subject_ids = [x.replace('WormBase:', 'WB:') if 'WormBase:' in x else x for x in subject_ids]
    slimmer_subjects = []
    mapped_ids = {}
    reverse_mapped_ids = {}
    for s in subject_ids:
        if 'HGNC:' in s or 'NCBIGene:' in s or 'ENSEMBL:' in s:
            prots = gene_to_uniprot_from_mygene(s)
            if len(prots) > 0:
                mapped_ids[s] = prots[0]
                reverse_mapped_ids[prots[0]] = s
                if len(prots) == 0:
                    prots = [s]
                slimmer_subjects += prots
        else:
            slimmer_subjects.append(s)

    print("SLIMMER SUBS : ", slimmer_subjects)
    subject_ids = slimmer_subjects

    # should remove any undefined subject
    for subject_id in subject_ids:
        if subject_id == "undefined":
            subject_ids.remove(subject_id)

    # because of the MGI:MGI
    mod_ids = []

    subjects = []
    for subject_id in subject_ids:

        entity = {"id": subject_id,
                  "groups": {},
                  "nb_classes": 0,
                  "nb_annotations": 0,
                  "terms": set()}

        if subject_id.startswith("MGI:"):
            subject_id = "MGI:" + subject_id
        mod_ids.append(subject_id)

        q = "*:*"
        qf = ""
        fq = "&fq=bioentity:\"" + subject_id + "\"&rows=100000"
        fields = "annotation_class,evidence_type,regulates_closure,aspect"
        if ecodes:
            fq += "&fq=evidence_type:(\"" + '" "'.join(ecodes) + "\")"
        elif exclude_IBA:
            fq += "&fq=!evidence_type:IBA"
        if exclude_PB:
            fq += "&fq=!annotation_class:\"GO:0005515\""
        print(fq)

        data = run_solr_text_on(ESOLR.GOLR, ESOLRDoc.ANNOTATION, q, qf, fields, fq)

        # compute number of terms and annotations
        for annot in data:
            aspect = aspect_map[annot["aspect"]]
            found = False

            for cat in categories:

                for gp in cat['groups']:
                    group = gp['id']

                    if gp['type'] == "Other":
                        continue

                    # only allow annotated terms belonging to the same category if cross_aspect
                    if cross_aspect or cat['id'] == aspect:

                        # is this annotation part of the current group, based on the regulates_closure ?
                        if group in annot['regulates_closure']:
                            found = True
                            break
            if found:
                entity['terms'].add(annot['annotation_class'])
                entity['nb_annotations'] += 1

        for cat in categories:

            for gp in cat['groups']:
                group = gp['id']

                if gp['type'] == "Other":
                    continue

                for annot in data:
                    aspect = aspect_map[annot["aspect"]]

                    # only allow annotated terms belonging to the same category if cross_aspect
                    if cross_aspect or cat['id'] == aspect:

                        # is this annotation part of the current group, based on the regulates_closure ?
                        if group in annot['regulates_closure']:

                            # if the group has not been met yet, create it
                            if group not in entity['groups']:
                                entity['groups'][group] = {}
                                entity['groups'][group]['ALL'] = {"terms": set(), "nb_classes": 0,
                                                                  "nb_annotations": 0}

                            # if the subgroup has not been met yet, create it
                            if annot['evidence_type'] not in entity['groups'][group]:
                                entity['groups'][group][annot['evidence_type']] = {"terms": set(), "nb_classes": 0,
                                                                                   "nb_annotations": 0}

                            # for each annotation, add the term and increment the nb of annotations
                            entity['groups'][group][annot['evidence_type']]['terms'].add(annot['annotation_class'])
                            entity['groups'][group][annot['evidence_type']]['nb_annotations'] += 1
                            entity['groups'][group]['ALL']['terms'].add(annot['annotation_class'])
                            entity['groups'][group]['ALL']['nb_annotations'] += 1

            terms = get_category_terms(cat)
            terms = [term["id"] for term in terms]

            other = {"ALL": {"terms": set(), "nb_classes": 0, "nb_annotations": 0}}

            for annot in data:
                aspect = aspect_map[annot["aspect"]]

                # only allow annotated terms belonging to the same category if cross_aspect
                if cross_aspect or cat['id'] == aspect:

                    found = False
                    for term in terms:
                        if term in annot["regulates_closure"]:
                            found = True
                            break

                    if not found:
                        other["ALL"]["nb_annotations"] += 1
                        other["ALL"]["terms"].add(annot['annotation_class'])
                        if annot['evidence_type'] not in other:
                            other[annot['evidence_type']] = {"terms": set(), "nb_classes": 0, "nb_annotations": 0}
                        other[annot['evidence_type']]["nb_annotations"] += 1
                        other[annot['evidence_type']]["terms"].add(annot['annotation_class'])

            entity['groups'][cat['id'] + "-other"] = other

        # compute the number of classes for each group that have subgroup (annotations)
        for group in entity['groups']:
            for subgroup in entity['groups'][group]:
                entity['groups'][group][subgroup]['nb_classes'] = len(entity['groups'][group][subgroup]['terms'])
                if "-other" not in group:
                    del entity['groups'][group][subgroup]['terms']
                else:
                    entity['groups'][group][subgroup]['terms'] = list(entity['groups'][group][subgroup]['terms'])

        entity['nb_classes'] = len(entity['terms'])
        del entity['terms']

        subjects.append(entity)

    # fill out the entity details
    q = "*:*"
    qf = ""
    fq = "&fq=bioentity:(\"" + "\" or \"".join(mod_ids) + "\")&rows=100000"
    fields = "bioentity,bioentity_label,taxon,taxon_label"
    data = run_solr_text_on(ESOLR.GOLR, ESOLRDoc.BIOENTITY, q, qf, fields, fq)

    for entity in subjects:
        for entity_detail in data:
            subject_id = entity_detail['bioentity'].replace("MGI:MGI:", "MGI:")

            if entity['id'] == subject_id:
                entity['label'] = entity_detail['bioentity_label']
                entity['taxon_id'] = entity_detail['taxon']
                entity['taxon_label'] = entity_detail['taxon_label']

    # map the entity back to their original IDs
    for entity in subjects:
        if entity['id'] in reverse_mapped_ids:
            entity['id'] = reverse_mapped_ids[entity['id']]

            # if any subject without annotation is retrieved, remove it
    to_remove = []
    for entity in subjects:
        if entity['nb_annotations'] == 0:
            to_remove.append(entity)

    for entity in to_remove:
        subjects.remove(entity)

    # http://golr-aux.geneontology.io/solr/select/?q=*:*&fq=document_category:%22bioentity%22&rows=10&wt=json&fl=bioentity,bioentity_label,taxon,taxon_label&fq=bioentity:(%22MGI:MGI:98214%22%20or%20%22RGD:620474%22)

    result = {"categories": categories, "subjects": subjects}
    return result


# this is a temporary json object, while waiting the
# ontology gets an annotation field to specify the order of a term in a slim
agr_slim_order = [
    {
        "category": "GO:0003674",
        "terms": [
            "GO:0003824",
            "GO:0030234",
            "GO:0038023",
            "GO:0005102",
            "GO:0005215",
            "GO:0005198",
            "GO:0008092",
            "GO:0003677",
            "GO:0003723",
            "GO:0003700",
            "GO:0008134",
            "GO:0036094",
            "GO:0046872",
            "GO:0030246",
            "GO:0097367",
            "GO:0008289"
        ]
    },

    {
        "category": "GO:0008150",
        "terms": [
            "GO:0007049",
            "GO:0016043",
            "GO:0051234",
            "GO:0008283",
            "GO:0030154",
            "GO:0008219",
            "GO:0032502",
            "GO:0000003",
            "GO:0002376",
            "GO:0050877",
            "GO:0050896",
            "GO:0023052",
            "GO:0006259",
            "GO:0016070",
            "GO:0019538",
            "GO:0005975",
            "GO:1901135",
            "GO:0006629",
            "GO:0042592",
            "GO:0009056",
            "GO:0007610"
        ]
    },

    {
        "category": "GO:0005575",
        "terms": [
            "GO:0005576",
            "GO:0005886",
            "GO:0045202",
            "GO:0030054",
            "GO:0042995",
            "GO:0031410",
            "GO:0005768",
            "GO:0005773",
            "GO:0005794",
            "GO:0005783",
            "GO:0005829",
            "GO:0005739",
            "GO:0005634",
            "GO:0005694",
            "GO:0005856",
            "GO:0032991"
        ]
    }
]


def go_summary(goid):
    goid = correct_goid(goid)
    return """
    PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
    PREFIX definition: <http://purl.obolibrary.org/obo/IAO_0000115>
    PREFIX obo: <http://www.geneontology.org/formats/oboInOwl#>

    SELECT ?goid ?label ?definition ?comment ?creation_date		(GROUP_CONCAT(distinct ?synonym;separator='""" + SEPARATOR + """') as ?synonyms)
                                                                (GROUP_CONCAT(distinct ?relatedSynonym;separator='""" + SEPARATOR + """') as ?relatedSynonyms)
                                                                (GROUP_CONCAT(distinct ?alternativeId;separator='""" + SEPARATOR + """') as ?alternativeIds)
                                                                (GROUP_CONCAT(distinct ?xref;separator='""" + SEPARATOR + """') as ?xrefs)
                                                                (GROUP_CONCAT(distinct ?subset;separator='""" + SEPARATOR + """') as ?subsets)

    WHERE {
        BIND(<http://purl.obolibrary.org/obo/""" + goid + """> as ?goid) .
        optional { ?goid rdfs:label ?label } .
        optional { ?goid definition: ?definition } .
        optional { ?goid rdfs:comment ?comment } .
        optional { ?goid obo:creation_date ?creation_date } .
        optional { ?goid obo:hasAlternativeId ?alternativeId } .
        optional { ?goid obo:hasRelatedSynonym ?relatedSynonym } .
        optional { ?goid obo:hasExactSynonym ?synonym } .
        optional { ?goid obo:hasDbXref ?xref } .
        optional { ?goid obo:inSubset ?subset } .
    }
    GROUP BY ?goid ?label ?definition ?comment ?creation_date
    """


def correct_goid(goid):
    return goid.replace(":", "_")


def get_go_subsets(self, goid):
    goid = correct_goid(self, goid)
    return """
    PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
    PREFIX obo: <http://www.geneontology.org/formats/oboInOwl#>

    SELECT ?label ?subset

    WHERE {
        BIND(<http://purl.obolibrary.org/obo/""" + goid + """> as ?goid) .
        optional { ?goid obo:inSubset ?subset .
                   ?subset rdfs:comment ?label } .
    }
    """