"""Ephemeral test-only signing key. Never used or configured by application code."""
import time,uuid
import jwt
from cryptography.hazmat.primitives.asymmetric import ec
PRIVATE_KEY=ec.generate_private_key(ec.SECP256R1())
PUBLIC_JWK=jwt.algorithms.ECAlgorithm.to_jwk(PRIVATE_KEY.public_key(),as_dict=True)
PUBLIC_JWK.update({'kid':'isolated-test-key','alg':'ES256','use':'sig','key_ops':['verify']})
PROJECT='https://sightline-test.supabase.co'
def issue_token(sub='00000000-0000-0000-0000-000000000001',email='operator@example.test',aud='authenticated',role='authenticated',exp_delta=3600,iss=None,secret=None,**changes):
    try:uuid.UUID(sub)
    except ValueError:sub=str(uuid.uuid5(uuid.NAMESPACE_DNS,sub))
    now=int(time.time())
    claims={'sub':sub,'email':email,'aud':aud,'role':role,'iat':now,'exp':now+exp_delta,'iss':iss or PROJECT+'/auth/v1'}
    claims.update(changes)
    key=ec.generate_private_key(ec.SECP256R1()) if secret else PRIVATE_KEY
    return jwt.encode(claims,key,algorithm='ES256',headers={'kid':'isolated-test-key'})
