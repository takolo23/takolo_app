import { parsePhoneNumberFromString, isSupportedCountry, type CountryCode } from "libphonenumber-js/max";
import { env } from "../config/env.js";
import { AppError } from "../http/errors.js";
export function normalizePhone(input: string, country = env.DEFAULT_PHONE_COUNTRY) {
  if (!isSupportedCountry(country)) throw new AppError(400, "El país predeterminado no es válido.");
  const clean = input.trim().replace(/^00/, "+");
  const phone = parsePhoneNumberFromString(clean, country as CountryCode);
  if (!phone?.isValid()) throw new AppError(400, "El teléfono no es válido. Usa código de país, por ejemplo +525512345678.", "INVALID_PHONE");
  return String(phone.number);
}
