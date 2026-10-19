from typing import Literal
from pydantic import BaseModel, Field, ConfigDict, model_validator

class ResponseContacts(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    securityName: str = Field(default='', max_length=80)
    securityPhone: str = Field(default='', pattern=r'^$|^\+?[1-9][0-9]{6,14}$')
    policePhone: str = Field(default='112', pattern=r'^\+?[0-9]{3,15}$')
    siteAddress: str = Field(default='', max_length=300)

class ResponseAction(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    eventId: str = Field(min_length=1, max_length=64, pattern=r'^[a-zA-Z0-9_-]+$')
    kind: Literal['call_opened', 'whatsapp_opened', 'summary_copied', 'summary_shared', 'contact_confirmed', 'note', 'resolved', 'false_alarm']
    recipient: Literal['security', 'police', 'owner'] = 'owner'
    detail: str = Field(default='', max_length=2000)

    @model_validator(mode='after')
    def validate_action(self):
        if self.kind in ('call_opened', 'contact_confirmed') and self.recipient not in ('security', 'police'):
            raise ValueError('Choose police or security for contact actions')
        if self.kind in ('whatsapp_opened', 'summary_shared') and self.recipient != 'security':
            raise ValueError('Sharing is supported for security')
        if self.kind == 'false_alarm' and self.detail not in ('Family member', 'Pet', 'Delivery', 'Model error', 'Other'):
            raise ValueError('Choose a false-alarm reason')
        if self.kind == 'note' and not self.detail:
            raise ValueError('Enter a note')
        return self
