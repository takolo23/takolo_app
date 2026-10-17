import { readFile } from "node:fs/promises";
import { getDMMF } from "@prisma/get-dmmf";

try {
  const path = new URL("../prisma/schema.prisma", import.meta.url);
  const datamodel = await readFile(path, "utf8");
  const dmmf = await getDMMF({ datamodel });
  console.log(
    `Esquema válido: ${dmmf.datamodel.models.length} modelos y ${dmmf.datamodel.enums.length} enumeraciones. Motor WASM oficial de Prisma; sin conexión a una base de datos.`,
  );
} catch (error) {
  console.error("No se pudo validar el esquema Prisma.");
  console.error(error instanceof Error ? error.message : String(error));
  process.exitCode = 1;
}
