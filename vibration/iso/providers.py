"""Pluggable reviewed user rules. No normative thresholds are supplied here."""
from dataclasses import dataclass,asdict
from datetime import date
from typing import Protocol
import copy
import re
from .contracts import Rule,MachineContext
from .evaluation import evaluate
from ..profiles import profile_digest


@dataclass(frozen=True)
class RuleDocument:
    rule: Rule
    edition: str
    source_uri: str
    source_sha256: str
    reviewed_by: str
    reviewed_on: str
    context_scope: dict

    def validate(self):
        self.rule.validate()
        for v in (self.edition,self.source_uri,self.reviewed_by,self.reviewed_on):
            if not isinstance(v,str) or not v.strip(): raise ValueError('Edition, source and review provenance required.')
        if not isinstance(self.source_sha256,str) or re.fullmatch('[0-9a-f]{64}',self.source_sha256) is None:
            raise ValueError('Source SHA256 required.')
        try: date.fromisoformat(self.reviewed_on)
        except ValueError as exc: raise ValueError('ISO review date required.') from exc
        if not isinstance(self.context_scope,dict) or not {'asset_id','machine','condition_id','location','operating_state'}<=set(self.context_scope):
            raise ValueError('Reviewed asset/machine/condition/location/state scope required.')
        if set(self.context_scope)-set(MachineContext.__dataclass_fields__): raise ValueError('Unknown context scope fields.')
        for k,v in self.context_scope.items():
            if v is None or v=='unknown' or (isinstance(v,str) and not v): raise ValueError('Concrete reviewed scope required: '+k)
        # Validate all scoped types using the same machinery as live contexts.
        MachineContext(**self.context_scope).validate()
        profile_digest(asdict(self))
        return self

    def matches(self,context):
        self.validate(); context.validate()
        return all(getattr(context,k)==v for k,v in self.context_scope.items())

    def provenance(self):
        self.validate()
        return {'edition':self.edition,'source_uri':self.source_uri,'source_sha256':self.source_sha256,
                'reviewed_by':self.reviewed_by,'reviewed_on':self.reviewed_on,
                'context_scope':copy.deepcopy(self.context_scope),'document_sha256':profile_digest(asdict(self)),
                'authority':'user_supplied_reviewed_rule','automatic_standard_selection':False}


class RuleProvider(Protocol):
    def resolve(self,standard:str,context:MachineContext) -> RuleDocument | None: ...


class MemoryRuleProvider:
    """Exact scoped selection; duplicates and ambiguous matches are errors."""
    def __init__(self,documents=()):
        self._documents=[]
        for document in documents: self.register(document)

    def register(self,document):
        if not isinstance(document,RuleDocument): raise TypeError('RuleDocument required.')
        document=copy.deepcopy(document); document.validate()
        if any((d.rule.standard,d.rule.key,d.edition,d.context_scope)==
               (document.rule.standard,document.rule.key,document.edition,document.context_scope) for d in self._documents):
            raise ValueError('Duplicate reviewed rule identity.')
        self._documents.append(document)

    def resolve(self,standard,context):
        context.validate()
        found=[d for d in self._documents if d.rule.standard==standard and d.matches(context)]
        if len(found)>1: raise ValueError('Ambiguous reviewed rules; select an explicit provider/edition.')
        return copy.deepcopy(found[0]) if found else None


def resolve_document(provider,standard,context):
    method=getattr(provider,'resolve',None)
    if not callable(method): raise TypeError('RuleProvider.resolve required.')
    document=method(standard,copy.deepcopy(context))
    if document is None: return None
    if not isinstance(document,RuleDocument): raise TypeError('Provider must return RuleDocument or None.')
    document=copy.deepcopy(document); document.validate()
    if document.rule.standard!=standard: raise ValueError('Provider returned a different rule identifier.')
    if not document.matches(context): return None
    return document


def evaluate_with_provider(standard,context,measurement,provider):
    context.validate(); measurement.validate()
    document=resolve_document(provider,standard,context)
    if document is None:
        return {'schema':'vibration.user-rule-evaluation.v1','status':'indeterminate','zone':None,
                'standard':standard,'asset_id':context.asset_id,'condition_id':context.condition_id,
                'point_id':measurement.point_id,'axis':measurement.axis,'reason':'reviewed_rule_scope_unavailable',
                'whole_machine_compliance':False,'automatic_shutdown':False}
    result=evaluate(standard,context,measurement,custom_rule=document.rule)
    return dict(result,rule_provenance=document.provenance())
