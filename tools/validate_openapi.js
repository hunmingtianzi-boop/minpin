const fs = require("fs");
const path = require("path");

const specPath = path.resolve(__dirname, "..", "packages", "contracts", "openapi.json");
const spec = JSON.parse(fs.readFileSync(specPath, "utf8"));
const errors = [];

if (typeof spec.openapi !== "string" || !spec.openapi.startsWith("3.1.")) {
  errors.push("openapi must be a 3.1.x document");
}

function decodePointer(value) {
  return value.replace(/~1/g, "/").replace(/~0/g, "~");
}

function resolveLocalRef(ref) {
  if (!ref.startsWith("#/")) {
    throw new Error(`external references are not allowed in the bootstrap contract: ${ref}`);
  }
  return ref
    .slice(2)
    .split("/")
    .map(decodePointer)
    .reduce((node, part) => {
      if (!node || !Object.prototype.hasOwnProperty.call(node, part)) {
        throw new Error(`unresolved reference: ${ref}`);
      }
      return node[part];
    }, spec);
}

function walk(value) {
  if (Array.isArray(value)) {
    value.forEach(walk);
    return;
  }
  if (!value || typeof value !== "object") return;
  if (typeof value.$ref === "string") {
    try {
      resolveLocalRef(value.$ref);
    } catch (error) {
      errors.push(error.message);
    }
  }
  Object.values(value).forEach(walk);
}

walk(spec);

const operationIds = [];
const methods = new Set(["get", "post", "put", "patch", "delete", "options", "head", "trace"]);
for (const [route, pathItem] of Object.entries(spec.paths || {})) {
  for (const [method, operation] of Object.entries(pathItem)) {
    if (!methods.has(method)) continue;
    if (!operation.operationId) {
      errors.push(`${method.toUpperCase()} ${route} is missing operationId`);
    } else {
      operationIds.push(operation.operationId);
    }
    if (!operation.responses || Object.keys(operation.responses).length === 0) {
      errors.push(`${method.toUpperCase()} ${route} is missing responses`);
    }
  }
}

const duplicates = operationIds.filter((id, index) => operationIds.indexOf(id) !== index);
if (duplicates.length) {
  errors.push(`duplicate operationId: ${[...new Set(duplicates)].join(", ")}`);
}

if (errors.length) {
  for (const error of errors) console.error(`ERROR: ${error}`);
  process.exit(1);
}

console.log(
  `OpenAPI bootstrap contract OK: ${Object.keys(spec.paths || {}).length} paths, ` +
    `${operationIds.length} operations, ${Object.keys(spec.components?.schemas || {}).length} schemas`,
);

