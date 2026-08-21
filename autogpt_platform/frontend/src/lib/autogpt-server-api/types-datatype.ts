/** Helpers to map BlockIO schemas to UI DataType. */

import {
  DataType,
  type BlockIOObjectSubSchema,
  type BlockIOStringSubSchema,
  type BlockIOSubSchema,
} from "./types-block";

const _stringFormatToDataTypeMap: Partial<Record<string, DataType>> = {
  date: DataType.DATE,
  time: DataType.TIME,
  file: DataType.FILE,
  "date-time": DataType.DATE_TIME,
  "short-text": DataType.SHORT_TEXT,
  "long-text": DataType.LONG_TEXT,
};

function _handleStringSchema(strSchema: BlockIOStringSubSchema): DataType {
  if (strSchema.format) {
    const type = _stringFormatToDataTypeMap[strSchema.format];
    if (type) return type;
  }
  if (strSchema.enum) return DataType.SELECT;
  if (strSchema.maxLength && strSchema.maxLength > 200)
    return DataType.LONG_TEXT;
  return DataType.SHORT_TEXT;
}

function _handleSingleTypeSchema(subSchema: BlockIOSubSchema): DataType {
  if (subSchema.type === "string") {
    return _handleStringSchema(subSchema as BlockIOStringSubSchema);
  }
  if (subSchema.type === "boolean") {
    return DataType.BOOLEAN;
  }
  if (subSchema.type === "number" || subSchema.type === "integer") {
    return DataType.NUMBER;
  }
  if (subSchema.type === "array") {
    // Check for table format first
    if ("format" in subSchema && subSchema.format === "table") {
      return DataType.TABLE;
    }
    /** Commented code below since we haven't yet support rendering of a multi-select with array { items: enum } type */
    // if ("items" in subSchema && subSchema.items && "enum" in subSchema.items) {
    //   return DataType.MULTI_SELECT; // array + enum => multi-select
    // }
    return DataType.ARRAY;
  }
  if (subSchema.type === "object") {
    if (
      ("additionalProperties" in subSchema && subSchema.additionalProperties) ||
      !("properties" in subSchema)
    ) {
      return DataType.KEY_VALUE; // if additionalProperties / no properties => key-value
    }
    if (
      Object.values(subSchema.properties).every(
        (prop) => prop.type === "boolean",
      )
    ) {
      return DataType.MULTI_SELECT; // if all props are boolean => multi-select
    }
    return DataType.OBJECT;
  }
  return DataType.SHORT_TEXT;
}

export function determineDataType(schema: BlockIOSubSchema): DataType {
  if ("allOf" in schema) {
    // If this happens, that is because Pydantic wraps $refs in an allOf if the
    // $ref has sibling schema properties (which isn't technically allowed),
    // so there will only be one item in allOf[].
    // this should NEVER happen though, as $refs are resolved server-side.
    console.warn(
      `Detected 'allOf' wrapper: ${schema}. Normalizing use ${schema.allOf[0]} instead.`,
    );
    schema = schema.allOf[0];
  }

  // Credentials override
  if ("credentials_provider" in schema) {
    return DataType.CREDENTIALS;
  }

  // enum == SELECT
  if ("enum" in schema) {
    return DataType.SELECT;
  }

  // Handle anyOf => optional types (string|null, number|null, etc.)
  if ("anyOf" in schema) {
    // e.g. schema.anyOf might look like [{ type: "string", ... }, { type: "null" }]
    const types = schema.anyOf.map((sub) =>
      "type" in sub ? sub.type : undefined,
    );

    // (string | null)
    if (types.includes("string") && types.includes("null")) {
      const strSchema = schema.anyOf.find(
        (s) => s.type === "string",
      ) as BlockIOStringSubSchema;
      return _handleStringSchema(strSchema);
    }

    // (number|integer) & null
    if (
      (types.includes("number") || types.includes("integer")) &&
      types.includes("null")
    ) {
      // Just reuse our single-type logic for whichever is not null
      const numSchema = schema.anyOf.find(
        (s) => s.type === "number" || s.type === "integer",
      );
      if (numSchema) {
        return _handleSingleTypeSchema(numSchema);
      }
      return DataType.NUMBER; // fallback
    }

    // (array | null)
    if (types.includes("array") && types.includes("null")) {
      // Check for table format on the parent schema (where anyOf is)
      if ("format" in schema && schema.format === "table") {
        return DataType.TABLE;
      }

      const arrSchema = schema.anyOf.find((s) => s.type === "array");
      if (arrSchema) return _handleSingleTypeSchema(arrSchema);
      return DataType.ARRAY;
    }

    // (object | null)
    if (types.includes("object") && types.includes("null")) {
      const objSchema = schema.anyOf.find(
        (s) => s.type === "object",
      ) as BlockIOObjectSubSchema;
      if (objSchema) return _handleSingleTypeSchema(objSchema);
      return DataType.OBJECT;
    }
  }

  // oneOf + discriminator => user picks which variant => SELECT
  if ("oneOf" in schema && "discriminator" in schema && schema.discriminator) {
    return DataType.SELECT;
  }

  // Direct type
  if ("type" in schema) {
    return _handleSingleTypeSchema(schema);
  }

  // Fallback
  return DataType.SHORT_TEXT;
}
