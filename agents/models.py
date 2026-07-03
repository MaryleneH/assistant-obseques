from datetime import datetime
from enum import Enum
from typing import List, Optional, Dict
from pydantic import BaseModel

class CeremonyStatus(str, Enum):
    draft = "draft"
    notes_added = "notes_added"
    extracted = "extracted"
    needs_review = "needs_review"
    ready_for_generation = "ready_for_generation"
    ceremony_generated = "ceremony_generated"
    quality_checked = "quality_checked"
    document_created = "document_created"
    email_draft_created = "email_draft_created"
    validated = "validated"
    archived = "archived"

class Deceased(BaseModel):
    firstName: Optional[str] = None
    lastName: Optional[str] = None
    age: Optional[int] = None
    personalityTraits: List[str] = []
    lifeElements: List[str] = []
    avoidMentioning: List[str] = []

class LiturgyStep(BaseModel):
    label: Optional[str] = None
    reference: Optional[str] = None
    title: Optional[str] = None
    detail: Optional[str] = None

class Ceremony(BaseModel):
    date: Optional[str] = None
    time: Optional[str] = None
    church: Optional[str] = None
    celebrant: Optional[str] = None
    liturgySteps: List[LiturgyStep] = []
    nextMass: Optional[str] = None
    entranceSong: Optional[str] = None
    firstReading: Optional[str] = None
    psalm: Optional[str] = None
    gospel: Optional[str] = None
    meditationSong: Optional[str] = None
    universalPrayerIntentions: List[str] = []
    finalFarewellSong: Optional[str] = None
    practicalNotes: List[str] = []

class ParticipantContact(BaseModel):
    name: Optional[str] = None
    relationship: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None

class Reader(BaseModel):
    name: Optional[str] = None
    relationship: Optional[str] = None
    task: Optional[str] = None

class Participants(BaseModel):
    mainFamilyContact: Optional[ParticipantContact] = None
    readers: List[Reader] = []
    prayerReaders: List[Reader] = []

class Communication(BaseModel):
    priestEmail: Optional[str] = None
    teamEmails: List[str] = []
    documentLink: Optional[str] = None
    emailSubject: Optional[str] = None
    emailBody: Optional[str] = None
    emailDraftCreated: bool = False

class Contradiction(BaseModel):
    field: Optional[str] = None
    values: List[str] = []
    pages: List[int] = []
    note: Optional[str] = None

class Extraction(BaseModel):
    sourceType: str = "manual_notes"
    pageCount: int = 1
    missingFields: List[str] = []
    contradictions: List[Contradiction] = []
    fieldConfidences: Dict[str, float] = {}
    needsHumanReview: List[str] = []

class QualityCheck(BaseModel):
    status: str = "PENDING"
    alerts: List[str] = []
    recommendedActions: List[str] = []
    suggestedQuestions: List[str] = []

class Security(BaseModel):
    containsSensitiveData: bool = True
    humanValidated: bool = False
    retentionPolicy: str = "delete_or_anonymize_after_defined_period"

class Record(BaseModel):
    caseId: str = ""
    status: CeremonyStatus = CeremonyStatus.draft
    createdAt: Optional[datetime] = None
    updatedAt: Optional[datetime] = None
    deceased: Deceased = Deceased()
    ceremony: Ceremony = Ceremony()
    participants: Participants = Participants()
    communication: Communication = Communication()
    extraction: Extraction = Extraction()
    qualityCheck: QualityCheck = QualityCheck()
    security: Security = Security()
