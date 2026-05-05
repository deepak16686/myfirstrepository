const fs = require('fs')
const path = require('path')

const defaultConnection = process.env.CHROMADB_ADMIN_DEFAULT_CONNECTION || 'http://chromadb:8000'
const defaultTenant = process.env.CHROMADB_ADMIN_DEFAULT_TENANT || 'default_tenant'
const defaultDatabase = process.env.CHROMADB_ADMIN_DEFAULT_DATABASE || 'default_database'

const normalizeConfigFunction =
  'let cfg=JSON.parse($item);if(!cfg.connectionString||/^https?:\\/\\/(localhost|127\\.0\\.0\\.1)(:\\d+)?\\/?$/.test(cfg.connectionString)){cfg.connectionString="$connection";window.localStorage.setItem($key,JSON.stringify(cfg))}cfg.tenant=cfg.tenant||"$tenant";cfg.database=cfg.database||"$database";cfg.authType=cfg.authType||"no_auth";return cfg'
    .replace('$connection', defaultConnection)
    .replace('$tenant', defaultTenant)
    .replace('$database', defaultDatabase)

function walk(dir) {
  if (!fs.existsSync(dir)) return []
  return fs.readdirSync(dir, { withFileTypes: true }).flatMap((entry) => {
    const fullPath = path.join(dir, entry.name)
    return entry.isDirectory() ? walk(fullPath) : [fullPath]
  })
}

const files = [...walk('/app/.next'), ...walk('/app/src')].filter((file) =>
  ['.js', '.html', '.ts', '.tsx'].includes(path.extname(file))
)

let patched = 0

for (const file of files) {
  let content = fs.readFileSync(file, 'utf8')
  const original = content

  content = content.replaceAll('http://localhost:8000', defaultConnection)
  content = content.replaceAll('placeholder="http://localhost:8000"', `placeholder="${defaultConnection}"`)

  content = content.replace(
    /function ([A-Za-z_$][\w$]*)\(\)\{let ([A-Za-z_$][\w$]*)=window\.localStorage\.getItem\(([A-Za-z_$][\w$]*)\);return \2\?JSON\.parse\(\2\):\{connectionString:"",currentCollection:"",authType:"no_auth",token:"",username:"",password:"",tenant:"default_tenant",database:"default_database"\}\}/g,
    (_match, fnName, itemName, keyName) =>
      `function ${fnName}(){let ${itemName}=window.localStorage.getItem(${keyName});if(${itemName}){${normalizeConfigFunction
        .replaceAll('$item', itemName)
        .replaceAll('$key', keyName)}}return {connectionString:"${defaultConnection}",currentCollection:"",authType:"no_auth",token:"",username:"",password:"",tenant:"${defaultTenant}",database:"${defaultDatabase}"}}`
  )

  content = content.replace(
    /function ([A-Za-z_$][\w$]*)\(e\)\{return new URLSearchParams\(new URL\(e\.url\)\.search\)\.get\("connectionString"\)\|\|""\}/g,
    (_match, fnName) =>
      `function ${fnName}(e){let t=new URLSearchParams(new URL(e.url).search).get("connectionString")||"";return !t||/^https?:\\/\\/(localhost|127\\.0\\.0\\.1)(:\\d+)?\\/?$/.test(t)?"${defaultConnection}":t.replace(/\\/$/,"")}`
  )

  content = content.replace(
    /function ([A-Za-z_$][\w$]*)\(e\)\{return new URLSearchParams\(new URL\(e\.url\)\.search\)\.get\("tenant"\)\|\|""\}/g,
    (_match, fnName) =>
      `function ${fnName}(e){return new URLSearchParams(new URL(e.url).search).get("tenant")||"${defaultTenant}"}`
  )

  content = content.replace(
    /function ([A-Za-z_$][\w$]*)\(e\)\{return new URLSearchParams\(new URL\(e\.url\)\.search\)\.get\("database"\)\|\|""\}/g,
    (_match, fnName) =>
      `function ${fnName}(e){return new URLSearchParams(new URL(e.url).search).get("database")||"${defaultDatabase}"}`
  )

  if (content !== original) {
    fs.writeFileSync(file, content)
    patched += 1
  }
}

if (patched === 0) {
  throw new Error('No ChromaDB Admin bundle files were patched')
}

console.log(`Patched ${patched} ChromaDB Admin files with default ${defaultConnection}`)
