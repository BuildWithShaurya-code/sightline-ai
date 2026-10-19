export interface SecuritySetup {
  propertyName: string; fullAddress: string; city: string; state: string; pinCode: string; landmark: string;
  contactName: string; phone: string; usePhoneForWhatsapp: boolean; whatsappPhone: string;
}
export type SetupErrors = Partial<Record<keyof SecuritySetup, string>>;
export const emptySecuritySetup: SecuritySetup = {propertyName:'',fullAddress:'',city:'',state:'',pinCode:'',landmark:'',contactName:'',phone:'',usePhoneForWhatsapp:true,whatsappPhone:''};
export function indianPhone(value: string): string {
  const compact=value.replace(/[\s()-]/g,'');
  const digits=compact.startsWith('+91')?compact.slice(3):compact.startsWith('91')&&compact.length===12?compact.slice(2):compact;
  return /^[1-9]\d{9}$/.test(digits)?`+91${digits}`:'';
}
export function validateSecuritySetup(input: SecuritySetup): {data:SecuritySetup;errors:SetupErrors} {
  const data={...input},errors:SetupErrors={};
  for(const key of ['propertyName','fullAddress','city','state','pinCode','landmark','contactName','phone','whatsappPhone'] as const)data[key]=typeof input[key]==='string'?input[key].trim():'';
  const required={propertyName:'Property name',fullAddress:'Full address',city:'City',state:'State',contactName:'Contact name'} as const;
  for(const key of Object.keys(required) as (keyof typeof required)[])if(!data[key])errors[key]=`${required[key]} is required.`;
  for(const key of ['propertyName','city','state','contactName'] as const)if(data[key].length>100)errors[key]='Use 100 characters or fewer.';
  if(data.fullAddress.length>500)errors.fullAddress='Use 500 characters or fewer.';
  if(data.landmark.length>200)errors.landmark='Use 200 characters or fewer.';
  if(!/^[1-9]\d{5}$/.test(data.pinCode))errors.pinCode='Enter a valid six-digit Indian PIN code.';
  const phone=indianPhone(data.phone);if(!phone)errors.phone='Enter a 10-digit Indian phone number.';else data.phone=phone;
  if(typeof data.usePhoneForWhatsapp!=='boolean')errors.usePhoneForWhatsapp='Choose whether to use the phone number for WhatsApp.';
  if(data.usePhoneForWhatsapp)data.whatsappPhone=phone;
  else {const whatsapp=indianPhone(data.whatsappPhone);if(!whatsapp)errors.whatsappPhone='Enter a 10-digit Indian WhatsApp number.';else data.whatsappPhone=whatsapp;}
  return {data,errors};
}
export const securitySetupComplete=(data:SecuritySetup|null)=>!!data&&!Object.keys(validateSecuritySetup(data).errors).length;
export function setupAddress(data:SecuritySetup):string {
  return [data.propertyName,data.fullAddress,data.city,data.state,data.pinCode,data.landmark?`Landmark: ${data.landmark}`:''].filter(Boolean).join(', ');
}
