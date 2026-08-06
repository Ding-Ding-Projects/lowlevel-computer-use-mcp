// desktop-material-managed-cheap-lfs-clone-helper:v1
import { constants, createReadStream } from 'node:fs'
import {
  chmod,
  lstat,
  link,
  mkdir,
  open,
  readdir,
  realpath,
  rename,
  rmdir,
  unlink,
} from 'node:fs/promises'
import { createHash, randomUUID } from 'node:crypto'
import { spawn } from 'node:child_process'
import { createInflateRaw } from 'node:zlib'
import {
  dirname,
  isAbsolute,
  join,
  relative,
  resolve,
  sep,
} from 'node:path'
import { fileURLToPath } from 'node:url'

const ManagedBy = 'desktop-material-cheap-lfs-clone-helper/v1'
const MaximumInventoryBytes = 8 * 1024 * 1024
const MaximumEntries = 4096
const MaximumPointerBytes = 1024 * 1024
const MaximumGhJsonBytes = 16 * 1024 * 1024
const MaximumGhErrorBytes = 1024 * 1024
const MaximumGhPrefixArguments = 8
const MaximumGhArgumentBytes = 4096
const NoFollowFlag = constants.O_NOFOLLOW ?? 0
const Sha256Pattern = /^[a-f0-9]{64}$/
const ControlCharacters = /[\u0000-\u001f]/
const InvalidWindowsSegmentCharacters = /[<>:"|?*\u0000-\u001f]/
const ReservedWindowsBasename =
  /^(?:con|prn|aux|nul|com[1-9]|lpt[1-9])(?:\..*)?$/i

class HydrationError extends Error {
  constructor(message, recoveryPaths = []) {
    super(message)
    this.name = 'HydrationError'
    this.recoveryPaths = recoveryPaths
  }
}

function byteLength(value) {
  return Buffer.byteLength(value, 'utf8')
}

function sha256(bytes) {
  return createHash('sha256').update(bytes).digest('hex')
}

function samePath(left, right) {
  const normalize = value =>
    process.platform === 'win32' ? resolve(value).toLowerCase() : resolve(value)
  return normalize(left) === normalize(right)
}

function isInside(root, candidate) {
  const rel = relative(root, candidate)
  return (
    rel === '' ||
    (rel !== '..' &&
      !rel.startsWith('..' + sep) &&
      !isAbsolute(rel))
  )
}

function pathIdentity(stats) {
  return {
    device: stats.dev,
    inode: stats.ino,
    birthtimeNanoseconds: stats.birthtimeNs,
    changeTimeNanoseconds: stats.ctimeNs,
    modificationTimeNanoseconds: stats.mtimeNs,
    sizeInBytes: stats.size,
    links: stats.nlink,
    mode: stats.mode,
  }
}

function sameIdentity(left, right) {
  return (
    left.device === right.device &&
    left.inode === right.inode &&
    left.birthtimeNanoseconds === right.birthtimeNanoseconds &&
    left.changeTimeNanoseconds === right.changeTimeNanoseconds &&
    left.modificationTimeNanoseconds === right.modificationTimeNanoseconds &&
    left.sizeInBytes === right.sizeInBytes &&
    left.links === right.links &&
    left.mode === right.mode
  )
}

function sameContentIdentity(left, right) {
  return (
    left.device === right.device &&
    left.inode === right.inode &&
    left.birthtimeNanoseconds === right.birthtimeNanoseconds &&
    left.modificationTimeNanoseconds === right.modificationTimeNanoseconds &&
    left.sizeInBytes === right.sizeInBytes &&
    left.mode === right.mode
  )
}

async function requireCanonicalDirectory(path, repositoryRoot = path) {
  const requested = resolve(path)
  // realpath expands ordinary Windows 8.3 names as well as links. Inspect each
  // visible path segment so short names remain usable without admitting a
  // symlink or junction anywhere in the requested chain.
  let ancestor = requested
  while (true) {
    const ancestorEntry = await lstat(ancestor, { bigint: true }).catch(
      () => null
    )
    if (ancestorEntry === null || ancestorEntry.isSymbolicLink()) {
      throw new HydrationError(
        'Cheap LFS refused a missing, linked, or non-directory path: ' +
          requested
      )
    }
    const parent = dirname(ancestor)
    if (parent === ancestor) {
      break
    }
    ancestor = parent
  }
  const before = await lstat(requested, { bigint: true }).catch(() => null)
  if (
    before === null ||
    before.isSymbolicLink() ||
    !before.isDirectory()
  ) {
    throw new HydrationError(
      'Cheap LFS refused a missing, linked, or non-directory path: ' + requested
    )
  }
  const canonical = await realpath(requested)
  const after = await lstat(canonical, { bigint: true })
  const containmentRoot = samePath(requested, repositoryRoot)
    ? canonical
    : repositoryRoot
  if (
    !isInside(containmentRoot, canonical) ||
    after.isSymbolicLink() ||
    !after.isDirectory() ||
    before.dev !== after.dev ||
    before.ino !== after.ino
  ) {
    throw new HydrationError(
      'Cheap LFS refused a redirected directory or junction: ' + requested
    )
  }
  return canonical
}

function validateRelativePath(input) {
  if (typeof input !== 'string' || input !== input.trim()) {
    return null
  }
  const normalized = input.replace(/\\/g, '/')
  const segments = normalized.split('/')
  if (
    normalized.length === 0 ||
    normalized.length > 4096 ||
    ControlCharacters.test(normalized) ||
    normalized.startsWith('/') ||
    /^[A-Za-z]:\//.test(normalized) ||
    segments.includes('.') ||
    segments.includes('..') ||
    segments.some(segment => segment.length === 0) ||
    segments.some(
      segment =>
        segment.length > 255 ||
        InvalidWindowsSegmentCharacters.test(segment) ||
        /[ .]$/.test(segment) ||
        ReservedWindowsBasename.test(segment)
    ) ||
    /^\.git/i.test(segments[0])
  ) {
    return null
  }
  return normalized
}

async function resolveTrackedPath(repositoryRoot, relativePath) {
  const normalized = validateRelativePath(relativePath)
  if (normalized === null) {
    throw new HydrationError(
      'Cheap LFS refused an unsafe inventory path: ' + String(relativePath)
    )
  }
  const segments = normalized.split('/')
  let parent = repositoryRoot
  for (const segment of segments.slice(0, -1)) {
    parent = await requireCanonicalDirectory(
      join(parent, segment),
      repositoryRoot
    )
  }
  const absolutePath = join(parent, segments[segments.length - 1])
  if (!isInside(repositoryRoot, absolutePath)) {
    throw new HydrationError(
      'Cheap LFS refused a tracked path outside the repository.'
    )
  }
  return { relativePath: normalized, absolutePath, parent }
}

async function readRegularFileBounded(path, maximumBytes) {
  const visible = await lstat(path, { bigint: true }).catch(() => null)
  if (
    visible === null ||
    visible.isSymbolicLink() ||
    !visible.isFile() ||
    visible.nlink !== 1n
  ) {
    throw new HydrationError(
      'Cheap LFS refused a missing, linked, or non-regular file: ' + path
    )
  }
  if (visible.size > BigInt(maximumBytes)) {
    throw new HydrationError(
      'Cheap LFS refused an oversized managed or pointer file: ' + path
    )
  }
  const handle = await open(path, constants.O_RDONLY | NoFollowFlag)
  try {
    const opened = await handle.stat({ bigint: true })
    if (
      !opened.isFile() ||
      opened.nlink !== 1n ||
      !sameIdentity(pathIdentity(visible), pathIdentity(opened))
    ) {
      throw new HydrationError(
        'Cheap LFS detected a file identity change while opening: ' + path
      )
    }
    const bytes = Buffer.alloc(Number(opened.size))
    let offset = 0
    while (offset < bytes.length) {
      const read = await handle.read(bytes, offset, bytes.length - offset, offset)
      if (read.bytesRead === 0) {
        throw new HydrationError(
          'Cheap LFS detected a truncated file while reading: ' + path
        )
      }
      offset += read.bytesRead
    }
    const after = await handle.stat({ bigint: true })
    const stillVisible = await lstat(path, { bigint: true })
    if (
      !sameIdentity(pathIdentity(opened), pathIdentity(after)) ||
      !sameIdentity(pathIdentity(opened), pathIdentity(stillVisible))
    ) {
      throw new HydrationError(
        'Cheap LFS detected a file change while reading: ' + path
      )
    }
    return { bytes, identity: pathIdentity(opened) }
  } finally {
    await handle.close()
  }
}

async function hashRegularFile(path, expectedSizeInBytes) {
  const visible = await lstat(path, { bigint: true }).catch(() => null)
  if (
    visible === null ||
    visible.isSymbolicLink() ||
    !visible.isFile() ||
    visible.nlink !== 1n ||
    visible.size !== BigInt(expectedSizeInBytes)
  ) {
    return null
  }
  const handle = await open(path, constants.O_RDONLY | NoFollowFlag)
  const digest = createHash('sha256')
  let total = 0
  try {
    const opened = await handle.stat({ bigint: true })
    if (!sameIdentity(pathIdentity(visible), pathIdentity(opened))) {
      throw new HydrationError(
        'Cheap LFS detected a file identity change while hashing: ' + path
      )
    }
    const stream = handle.createReadStream({ autoClose: false })
    for await (const chunk of stream) {
      digest.update(chunk)
      total += chunk.length
    }
    const after = await handle.stat({ bigint: true })
    const stillVisible = await lstat(path, { bigint: true })
    if (
      total !== expectedSizeInBytes ||
      !sameIdentity(pathIdentity(opened), pathIdentity(after)) ||
      !sameIdentity(pathIdentity(opened), pathIdentity(stillVisible))
    ) {
      throw new HydrationError(
        'Cheap LFS detected a file change while hashing: ' + path
      )
    }
    return digest.digest('hex')
  } finally {
    await handle.close()
  }
}

function requireSafeInteger(value, label, allowZero = true) {
  if (
    !Number.isSafeInteger(value) ||
    value < (allowZero ? 0 : 1)
  ) {
    throw new HydrationError('Cheap LFS inventory has an invalid ' + label + '.')
  }
  return value
}

function requireDigest(value, label) {
  if (typeof value !== 'string' || !Sha256Pattern.test(value)) {
    throw new HydrationError('Cheap LFS inventory has an invalid ' + label + '.')
  }
  return value
}

function requireAssetName(value) {
  if (
    typeof value !== 'string' ||
    value.length === 0 ||
    value.length > 255 ||
    ControlCharacters.test(value)
  ) {
    throw new HydrationError(
      'Cheap LFS inventory has an invalid GitHub Release asset name.'
    )
  }
  return value
}

function validateInventory(parsed) {
  if (
    parsed === null ||
    typeof parsed !== 'object' ||
    parsed.managedBy !== ManagedBy ||
    parsed.schemaVersion !== 1 ||
    !Array.isArray(parsed.entries) ||
    parsed.entries.length > MaximumEntries
  ) {
    throw new HydrationError(
      'Cheap LFS inventory is not a supported bounded managed inventory.'
    )
  }
  const paths = new Set()
  return parsed.entries.map(raw => {
    if (raw === null || typeof raw !== 'object') {
      throw new HydrationError('Cheap LFS inventory contains a non-object entry.')
    }
    const path = validateRelativePath(raw.path)
    if (path === null) {
      throw new HydrationError(
        'Cheap LFS inventory contains an unsafe tracked path.'
      )
    }
    const pathKey = path.toLowerCase()
    if (paths.has(pathKey)) {
      throw new HydrationError(
        'Cheap LFS inventory contains duplicate or case-colliding paths.'
      )
    }
    paths.add(pathKey)
    if (
      typeof raw.pointerText !== 'string' ||
      byteLength(raw.pointerText) > MaximumPointerBytes ||
      sha256(Buffer.from(raw.pointerText, 'utf8')) !== raw.pointerSha256
    ) {
      throw new HydrationError(
        'Cheap LFS inventory pointer identity is invalid for ' + path + '.'
      )
    }
    const sizeInBytes = requireSafeInteger(
      raw.sizeInBytes,
      'whole-object size'
    )
    const objectSha256 = requireDigest(
      raw.sha256,
      'whole-object SHA-256'
    )
    const source = raw.source
    if (source === null || typeof source !== 'object') {
      throw new HydrationError(
        'Cheap LFS inventory source is missing for ' + path + '.'
      )
    }
    if (source.provider === 'github-release') {
      if (
        typeof source.releaseTag !== 'string' ||
        source.releaseTag.length === 0 ||
        source.releaseTag.length > 255 ||
        /\s/.test(source.releaseTag) ||
        !Array.isArray(source.parts) ||
        source.parts.length === 0 ||
        source.parts.length > MaximumEntries
      ) {
        throw new HydrationError(
          'Cheap LFS inventory has invalid Release metadata for ' + path + '.'
        )
      }
      let total = 0
      const parts = source.parts.map(part => {
        if (part === null || typeof part !== 'object') {
          throw new HydrationError(
            'Cheap LFS inventory has an invalid Release part for ' + path + '.'
          )
        }
        const encoding = part.encoding
        if (encoding !== 'raw' && encoding !== 'deflate-raw') {
          throw new HydrationError(
            'Cheap LFS inventory has an unsupported Release encoding for ' +
              path +
              '.'
          )
        }
        const partSize = requireSafeInteger(
          part.sizeInBytes,
          'Release part size'
        )
        const storedSize = requireSafeInteger(
          part.storedSizeInBytes,
          'stored Release part size'
        )
        if (
          (encoding === 'raw' && storedSize !== partSize) ||
          (encoding === 'deflate-raw' &&
            (storedSize < 1 || storedSize >= partSize))
        ) {
          throw new HydrationError(
            'Cheap LFS inventory has inconsistent Release part sizes for ' +
              path +
              '.'
          )
        }
        total += partSize
        if (!Number.isSafeInteger(total)) {
          throw new HydrationError(
            'Cheap LFS inventory Release sizes overflow for ' + path + '.'
          )
        }
        return {
          assetName: requireAssetName(part.assetName),
          encoding,
          sizeInBytes: partSize,
          storedSizeInBytes: storedSize,
          sha256: requireDigest(part.sha256, 'Release part SHA-256'),
        }
      })
      if (total !== sizeInBytes) {
        throw new HydrationError(
          'Cheap LFS inventory Release parts do not match the whole size for ' +
            path +
            '.'
        )
      }
      return {
        path,
        pointerText: raw.pointerText,
        pointerSha256: raw.pointerSha256,
        sizeInBytes,
        sha256: objectSha256,
        source: {
          provider: 'github-release',
          releaseTag: source.releaseTag,
          parts,
        },
      }
    }
    if (source.provider === 'encrypted-github-release') {
      return {
        path,
        pointerText: raw.pointerText,
        pointerSha256: raw.pointerSha256,
        sizeInBytes,
        sha256: objectSha256,
        source: {
          provider: 'encrypted-github-release',
          releaseTag:
            typeof source.releaseTag === 'string' ? source.releaseTag : '',
        },
      }
    }
    if (source.provider === 'oci') {
      return {
        path,
        pointerText: raw.pointerText,
        pointerSha256: raw.pointerSha256,
        sizeInBytes,
        sha256: objectSha256,
        source: {
          provider: 'oci',
          registryProvider:
            source.registryProvider === 'docker-hub'
              ? 'docker-hub'
              : 'ghcr',
          image: typeof source.image === 'string' ? source.image : '',
        },
      }
    }
    throw new HydrationError(
      'Cheap LFS inventory has an unknown provider for ' + path + '.'
    )
  })
}

function parseArguments(argv) {
  const selected = []
  let listOnly = false
  for (let index = 0; index < argv.length; index++) {
    const argument = argv[index]
    if (argument === '--list') {
      listOnly = true
      continue
    }
    if (argument === '--path') {
      const value = argv[++index]
      if (value === undefined) {
        throw new HydrationError('Cheap LFS --path needs a repository path.')
      }
      selected.push(value)
      continue
    }
    if (argument.startsWith('--')) {
      throw new HydrationError(
        'Cheap LFS does not recognize helper option ' + argument + '.'
      )
    }
    selected.push(argument)
  }
  return { selected, listOnly }
}

function ghInvocation(argumentsForGh) {
  const executable =
    process.env.DESKTOP_MATERIAL_CHEAP_LFS_GH_EXECUTABLE || 'gh'
  if (
    typeof executable !== 'string' ||
    executable.length === 0 ||
    executable.includes('\0')
  ) {
    throw new HydrationError('Cheap LFS received an invalid gh executable path.')
  }
  let prefix = []
  const encodedPrefix =
    process.env.DESKTOP_MATERIAL_CHEAP_LFS_GH_PREFIX_ARGS_JSON
  if (encodedPrefix !== undefined) {
    try {
      prefix = JSON.parse(encodedPrefix)
    } catch {
      throw new HydrationError(
        'Cheap LFS received invalid gh prefix-argument JSON.'
      )
    }
    if (
      !Array.isArray(prefix) ||
      prefix.length > MaximumGhPrefixArguments ||
      prefix.some(
        value =>
          typeof value !== 'string' ||
          value.length === 0 ||
          byteLength(value) > MaximumGhArgumentBytes ||
          value.includes('\0')
      )
    ) {
      throw new HydrationError(
        'Cheap LFS received unsafe gh prefix arguments.'
      )
    }
  }
  return { executable, arguments: [...prefix, ...argumentsForGh] }
}

function safeGhFailure(stderr) {
  const text = stderr.toString('utf8').trim()
  return text.length === 0
    ? 'GitHub CLI returned no diagnostic.'
    : text.slice(-4096)
}

async function runGhCapture(repositoryRoot, argumentsForGh, maximumBytes) {
  const invocation = ghInvocation(argumentsForGh)
  const child = spawn(invocation.executable, invocation.arguments, {
    cwd: repositoryRoot,
    env: process.env,
    shell: false,
    stdio: ['ignore', 'pipe', 'pipe'],
    windowsHide: true,
  })
  const stdout = []
  const stderr = []
  let stdoutBytes = 0
  let stderrBytes = 0
  let overflow = false
  child.stdout.on('data', chunk => {
    stdoutBytes += chunk.length
    if (stdoutBytes > maximumBytes) {
      overflow = true
      child.kill()
      return
    }
    stdout.push(chunk)
  })
  child.stderr.on('data', chunk => {
    stderrBytes += chunk.length
    if (stderrBytes > MaximumGhErrorBytes) {
      overflow = true
      child.kill()
      return
    }
    stderr.push(chunk)
  })
  const outcome = await new Promise((resolveOutcome, rejectOutcome) => {
    child.once('error', rejectOutcome)
    child.once('close', (code, signal) =>
      resolveOutcome({ code, signal })
    )
  }).catch(error => {
    if (error && error.code === 'ENOENT') {
      throw new HydrationError(
        'GitHub CLI was not found. Install gh, authenticate if needed, and rerun the helper.'
      )
    }
    throw error
  })
  if (overflow) {
    throw new HydrationError('GitHub CLI returned an oversized response.')
  }
  if (outcome.code !== 0 || outcome.signal !== null) {
    throw new HydrationError(
      'GitHub CLI request failed: ' +
        safeGhFailure(Buffer.concat(stderr))
    )
  }
  return Buffer.concat(stdout)
}

async function resolveGithubRepository(repositoryRoot) {
  const response = await runGhCapture(
    repositoryRoot,
    ['repo', 'view', '--json', 'nameWithOwner'],
    64 * 1024
  )
  let parsed
  try {
    parsed = JSON.parse(response.toString('utf8'))
  } catch {
    throw new HydrationError(
      'GitHub CLI did not return valid repository identity JSON.'
    )
  }
  if (
    typeof parsed.nameWithOwner !== 'string' ||
    !/^[A-Za-z0-9_.-]+\/[A-Za-z0-9_.-]+$/.test(parsed.nameWithOwner)
  ) {
    throw new HydrationError(
      'GitHub CLI could not identify this clone as one GitHub repository.'
    )
  }
  return parsed.nameWithOwner
}

async function getRelease(
  repositoryRoot,
  repository,
  releaseTag,
  cache
) {
  const cached = cache.get(releaseTag)
  if (cached !== undefined) {
    return cached
  }
  const endpoint =
    'repos/' +
    repository +
    '/releases/tags/' +
    encodeURIComponent(releaseTag)
  const response = await runGhCapture(
    repositoryRoot,
    ['api', endpoint],
    MaximumGhJsonBytes
  )
  let parsed
  try {
    parsed = JSON.parse(response.toString('utf8'))
  } catch {
    throw new HydrationError(
      'GitHub CLI returned invalid Release metadata for tag ' +
        releaseTag +
        '.'
    )
  }
  if (!Array.isArray(parsed.assets)) {
    throw new HydrationError(
      'GitHub Release metadata has no asset inventory for tag ' +
        releaseTag +
        '.'
    )
  }
  cache.set(releaseTag, parsed)
  return parsed
}

async function findReleaseAsset(
  repositoryRoot,
  repository,
  releaseTag,
  assetName,
  expectedSizeInBytes,
  cache
) {
  const release = await getRelease(
    repositoryRoot,
    repository,
    releaseTag,
    cache
  )
  const matches = release.assets.filter(asset => asset.name === assetName)
  if (matches.length !== 1) {
    throw new HydrationError(
      'GitHub Release ' +
        releaseTag +
        ' does not contain exactly one asset named ' +
        assetName +
        '.'
    )
  }
  const asset = matches[0]
  if (
    !Number.isSafeInteger(asset.id) ||
    asset.id < 1 ||
    asset.size !== expectedSizeInBytes
  ) {
    throw new HydrationError(
      'GitHub Release asset metadata does not match the pointer for ' +
        assetName +
        '.'
    )
  }
  return asset.id
}

async function downloadReleaseAsset(
  repositoryRoot,
  repository,
  assetId,
  destination,
  expectedSizeInBytes
) {
  const handle = await open(
    destination,
    constants.O_WRONLY |
      constants.O_CREAT |
      constants.O_EXCL |
      NoFollowFlag,
    0o600
  )
  const invocation = ghInvocation([
    'api',
    'repos/' + repository + '/releases/assets/' + assetId,
    '--header',
    'Accept: application/octet-stream',
  ])
  const child = spawn(invocation.executable, invocation.arguments, {
    cwd: repositoryRoot,
    env: process.env,
    shell: false,
    stdio: ['ignore', 'pipe', 'pipe'],
    windowsHide: true,
  })
  const stderr = []
  let stderrBytes = 0
  let transferred = 0
  let overflow = false
  child.stderr.on('data', chunk => {
    stderrBytes += chunk.length
    if (stderrBytes > MaximumGhErrorBytes) {
      overflow = true
      child.kill()
      return
    }
    stderr.push(chunk)
  })
  let closed = false
  try {
    const childOutcome = new Promise((resolveOutcome, rejectOutcome) => {
      child.once('error', rejectOutcome)
      child.once('close', (code, signal) =>
        resolveOutcome({ code, signal })
      )
    })
    const transfer = (async () => {
      for await (const chunk of child.stdout) {
        const nextTransferred = transferred + chunk.length
        if (nextTransferred > expectedSizeInBytes) {
          overflow = true
          child.kill()
          throw new HydrationError(
            'GitHub Release asset exceeded its exact pointer size.'
          )
        }
        await writeAll(handle, chunk, transferred)
        transferred = nextTransferred
      }
    })()
    const [outcome] = await Promise.all([
      childOutcome,
      transfer,
    ])
    if (
      overflow ||
      transferred !== expectedSizeInBytes ||
      outcome.code !== 0 ||
      outcome.signal !== null
    ) {
      throw new HydrationError(
        outcome.code === 0 && outcome.signal === null
          ? 'GitHub Release asset did not match its exact stored size.'
          : 'GitHub CLI asset download failed: ' +
              safeGhFailure(Buffer.concat(stderr))
      )
    }
    await handle.sync()
    await handle.close()
    closed = true
    const downloaded = await lstat(destination, { bigint: true })
    if (
      downloaded.isSymbolicLink() ||
      !downloaded.isFile() ||
      downloaded.nlink !== 1n ||
      downloaded.size !== BigInt(expectedSizeInBytes)
    ) {
      throw new HydrationError(
        'Downloaded Cheap LFS sidecar failed its file identity check.'
      )
    }
  } catch (error) {
    child.kill()
    if (!closed) {
      await handle.close().catch(() => undefined)
    }
    throw error
  }
}

async function writeAll(handle, bytes, position) {
  let written = 0
  while (written < bytes.length) {
    const result = await handle.write(
      bytes,
      written,
      bytes.length - written,
      position + written
    )
    if (result.bytesWritten < 1) {
      throw new HydrationError(
        'Cheap LFS could not write its verified materialization sidecar.'
      )
    }
    written += result.bytesWritten
  }
}

async function appendVerifiedPart(
  downloadedPath,
  part,
  outputHandle,
  outputOffset,
  wholeHash
) {
  const stored = await lstat(downloadedPath, { bigint: true })
  if (
    stored.isSymbolicLink() ||
    !stored.isFile() ||
    stored.nlink !== 1n ||
    stored.size !== BigInt(part.storedSizeInBytes)
  ) {
    throw new HydrationError(
      'Cheap LFS downloaded sidecar changed before verification.'
    )
  }
  const source = createReadStream(downloadedPath)
  const decoded =
    part.encoding === 'deflate-raw'
      ? source.pipe(createInflateRaw())
      : source
  const partHash = createHash('sha256')
  let partBytes = 0
  for await (const chunk of decoded) {
    partBytes += chunk.length
    if (partBytes > part.sizeInBytes) {
      throw new HydrationError(
        'Cheap LFS decoded part exceeded its exact pointer size.'
      )
    }
    partHash.update(chunk)
    wholeHash.update(chunk)
    await writeAll(outputHandle, chunk, outputOffset + partBytes - chunk.length)
  }
  if (
    partBytes !== part.sizeInBytes ||
    partHash.digest('hex') !== part.sha256
  ) {
    throw new HydrationError(
      'Cheap LFS decoded part failed exact size or SHA-256 verification.'
    )
  }
  return partBytes
}

async function assertPointerStillMatches(proof, entry) {
  const current = await readRegularFileBounded(
    proof.absolutePath,
    MaximumPointerBytes
  )
  if (
    !sameIdentity(proof.identity, current.identity) ||
    !current.bytes.equals(Buffer.from(entry.pointerText, 'utf8')) ||
    sha256(current.bytes) !== entry.pointerSha256
  ) {
    throw new HydrationError(
      'Cheap LFS pointer changed before materialization: ' + entry.path
    )
  }
}

async function safeCleanupRecovery(
  recoveryPath,
  recoveryIdentity,
  allowedNames
) {
  const current = await lstat(recoveryPath, { bigint: true }).catch(() => null)
  if (
    current === null ||
    current.isSymbolicLink() ||
    !current.isDirectory() ||
    current.dev !== recoveryIdentity.device ||
    current.ino !== recoveryIdentity.inode
  ) {
    return false
  }
  const names = await readdir(recoveryPath)
  if (names.some(name => !allowedNames.has(name))) {
    return false
  }
  for (const name of names) {
    const childPath = join(recoveryPath, name)
    const child = await lstat(childPath, { bigint: true }).catch(() => null)
    if (
      child === null ||
      child.isSymbolicLink() ||
      !child.isFile() ||
      child.nlink !== 1n
    ) {
      return false
    }
  }
  for (const name of names) {
    await unlink(join(recoveryPath, name))
  }
  await rmdir(recoveryPath)
  return true
}

async function publishVerifiedReplacement(
  proof,
  entry,
  recoveryPath,
  replacementPath
) {
  await assertPointerStillMatches(proof, entry)
  const originalPath = join(recoveryPath, 'original-pointer')
  let quarantined = false
  try {
    await rename(proof.absolutePath, originalPath)
    quarantined = true
    const original = await readRegularFileBounded(
      originalPath,
      MaximumPointerBytes
    )
    if (
      !sameContentIdentity(proof.identity, original.identity) ||
      !original.bytes.equals(Buffer.from(entry.pointerText, 'utf8'))
    ) {
      throw new HydrationError(
        'Cheap LFS pointer changed at the materialization boundary.'
      )
    }
    await link(replacementPath, proof.absolutePath)
    const published = await lstat(proof.absolutePath, { bigint: true })
    const staged = await lstat(replacementPath, { bigint: true })
    if (
      !published.isFile() ||
      !staged.isFile() ||
      published.nlink !== 2n ||
      staged.nlink !== 2n ||
      published.dev !== staged.dev ||
      published.ino !== staged.ino
    ) {
      throw new HydrationError(
        'Cheap LFS could not prove its atomic materialization link.'
      )
    }
    await unlink(originalPath)
    quarantined = false
    await unlink(replacementPath)
    const final = await lstat(proof.absolutePath, { bigint: true })
    if (
      final.isSymbolicLink() ||
      !final.isFile() ||
      final.nlink !== 1n ||
      final.size !== BigInt(entry.sizeInBytes)
    ) {
      throw new HydrationError(
        'Cheap LFS materialized file failed its final identity check.',
        [recoveryPath]
      )
    }
    await rmdir(recoveryPath)
  } catch (error) {
    if (quarantined) {
      const occupant = await lstat(proof.absolutePath).catch(() => null)
      if (occupant === null) {
        try {
          await link(originalPath, proof.absolutePath)
          await unlink(originalPath)
          quarantined = false
        } catch {
          throw new HydrationError(
            'Cheap LFS preserved the original pointer and sidecar for recovery at ' +
              recoveryPath +
              '.',
            [recoveryPath]
          )
        }
      }
    }
    if (quarantined) {
      throw new HydrationError(
        'Cheap LFS refused to overwrite a concurrent destination; the original pointer is preserved at ' +
          recoveryPath +
          '.',
        [recoveryPath]
      )
    }
    throw error
  }
}

async function inspectEntry(repositoryRoot, entry) {
  const location = await resolveTrackedPath(repositoryRoot, entry.path)
  const visible = await lstat(location.absolutePath, {
    bigint: true,
  }).catch(() => null)
  if (
    visible === null ||
    visible.isSymbolicLink() ||
    !visible.isFile() ||
    visible.nlink !== 1n
  ) {
    throw new HydrationError(
      'Cheap LFS refused a missing, linked, or non-regular tracked file: ' +
        entry.path
    )
  }
  if (visible.size <= BigInt(MaximumPointerBytes)) {
    const candidate = await readRegularFileBounded(
      location.absolutePath,
      MaximumPointerBytes
    )
    if (
      candidate.bytes.equals(Buffer.from(entry.pointerText, 'utf8')) &&
      sha256(candidate.bytes) === entry.pointerSha256
    ) {
      return {
        state: 'pointer',
        absolutePath: location.absolutePath,
        parent: location.parent,
        identity: candidate.identity,
      }
    }
  }
  if (visible.size === BigInt(entry.sizeInBytes)) {
    const digest = await hashRegularFile(
      location.absolutePath,
      entry.sizeInBytes
    )
    if (digest === entry.sha256) {
      return {
        state: 'hydrated',
        absolutePath: location.absolutePath,
        parent: location.parent,
      }
    }
  }
  throw new HydrationError(
    'Cheap LFS left a modified or stale tracked file untouched: ' + entry.path
  )
}

function unsupportedProviderMessage(entry) {
  if (entry.source.provider === 'encrypted-github-release') {
    return (
      'Cannot hydrate "' +
      entry.path +
      '": this helper does not support encrypted GitHub Release pointers. ' +
      'Open this repository in Desktop Material, choose Large files & storage, ' +
      'and restore the file there with the repository Cheap LFS password.'
    )
  }
  return (
    'Cannot hydrate "' +
    entry.path +
    '": this helper does not support Cheap LFS ' +
    entry.source.registryProvider +
    ' OCI pointers. Open this repository in Desktop Material, choose Large ' +
    'files & storage, and restore the file there so the immutable manifest, ' +
    'layer digests, and repository key are validated.'
  )
}

async function materializeReleaseEntry(
  repositoryRoot,
  repository,
  entry,
  proof,
  releaseCache
) {
  const recoveryPath = join(
    proof.parent,
    '.cheap-lfs-hydrate-' + process.pid + '-' + randomUUID()
  )
  await mkdir(recoveryPath, { mode: 0o700 })
  const recovery = await lstat(recoveryPath, { bigint: true })
  if (recovery.isSymbolicLink() || !recovery.isDirectory()) {
    throw new HydrationError(
      'Cheap LFS could not create a private materialization sidecar directory.'
    )
  }
  const recoveryIdentity = {
    device: recovery.dev,
    inode: recovery.ino,
  }
  const replacementPath = join(recoveryPath, 'verified-payload')
  const allowedNames = new Set(['verified-payload'])
  let outputHandle
  let published = false
  try {
    outputHandle = await open(
      replacementPath,
      constants.O_WRONLY |
        constants.O_CREAT |
        constants.O_EXCL |
        NoFollowFlag,
      Number(proof.identity.mode & 0o777n)
    )
    const wholeHash = createHash('sha256')
    let outputOffset = 0
    for (let index = 0; index < entry.source.parts.length; index++) {
      const part = entry.source.parts[index]
      const assetId = await findReleaseAsset(
        repositoryRoot,
        repository,
        entry.source.releaseTag,
        part.assetName,
        part.storedSizeInBytes,
        releaseCache
      )
      const downloadedName = 'download-' + index
      const downloadedPath = join(recoveryPath, downloadedName)
      allowedNames.add(downloadedName)
      await downloadReleaseAsset(
        repositoryRoot,
        repository,
        assetId,
        downloadedPath,
        part.storedSizeInBytes
      )
      outputOffset += await appendVerifiedPart(
        downloadedPath,
        part,
        outputHandle,
        outputOffset,
        wholeHash
      )
      await unlink(downloadedPath)
      allowedNames.delete(downloadedName)
    }
    await outputHandle.sync()
    await outputHandle.close()
    outputHandle = undefined
    if (
      outputOffset !== entry.sizeInBytes ||
      wholeHash.digest('hex') !== entry.sha256
    ) {
      throw new HydrationError(
        'Cheap LFS payload failed exact whole-file size or SHA-256 verification.'
      )
    }
    const replacement = await lstat(replacementPath, { bigint: true })
    if (
      replacement.isSymbolicLink() ||
      !replacement.isFile() ||
      replacement.nlink !== 1n ||
      replacement.size !== BigInt(entry.sizeInBytes)
    ) {
      throw new HydrationError(
        'Cheap LFS verified sidecar failed its identity check.'
      )
    }
    await chmod(replacementPath, Number(proof.identity.mode & 0o777n))
    await publishVerifiedReplacement(
      proof,
      entry,
      recoveryPath,
      replacementPath
    )
    published = true
  } finally {
    if (outputHandle !== undefined) {
      await outputHandle.close().catch(() => undefined)
    }
    if (!published) {
      const cleaned = await safeCleanupRecovery(
        recoveryPath,
        recoveryIdentity,
        allowedNames
      ).catch(() => false)
      if (!cleaned) {
        const remaining = await lstat(recoveryPath).catch(() => null)
        if (remaining !== null) {
          console.error(
            'Cheap LFS preserved uncertain recovery files at ' + recoveryPath
          )
        }
      }
    }
  }
}

async function loadInventory(repositoryRoot) {
  const helperDirectory = await requireCanonicalDirectory(
    join(repositoryRoot, '.desktop-material', 'cheap-lfs'),
    repositoryRoot
  )
  const inventoryPath = join(helperDirectory, 'hydrate-inventory.json')
  const inventory = await readRegularFileBounded(
    inventoryPath,
    MaximumInventoryBytes
  )
  let parsed
  try {
    parsed = JSON.parse(inventory.bytes.toString('utf8'))
  } catch {
    throw new HydrationError('Cheap LFS inventory is not valid JSON.')
  }
  return validateInventory(parsed)
}

async function main() {
  const scriptDirectory = dirname(fileURLToPath(import.meta.url))
  const requestedRoot = resolve(scriptDirectory, '..', '..')
  const repositoryRoot = await requireCanonicalDirectory(requestedRoot)
  const entries = await loadInventory(repositoryRoot)
  const options = parseArguments(process.argv.slice(2))
  if (options.listOnly) {
    for (const entry of entries) {
      console.log(entry.path)
    }
    return
  }
  const byPath = new Map(entries.map(entry => [entry.path.toLowerCase(), entry]))
  const selected =
    options.selected.length === 0
      ? entries
      : options.selected.map(input => {
          const path = validateRelativePath(input)
          const entry = path === null ? undefined : byPath.get(path.toLowerCase())
          if (entry === undefined) {
            throw new HydrationError(
              'Cheap LFS inventory does not contain selected path ' +
                String(input) +
                '.'
            )
          }
          return entry
        })
  const unique = []
  const selectedPaths = new Set()
  for (const entry of selected) {
    const key = entry.path.toLowerCase()
    if (!selectedPaths.has(key)) {
      selectedPaths.add(key)
      unique.push(entry)
    }
  }
  const inspected = new Map()
  const alreadyHydrated = []
  for (const entry of unique) {
    const state = await inspectEntry(repositoryRoot, entry)
    inspected.set(entry.path, state)
    if (state.state === 'hydrated') {
      alreadyHydrated.push(entry.path)
    }
  }
  const pending = unique.filter(
    entry => inspected.get(entry.path).state === 'pointer'
  )
  const unsupported = pending
    .filter(entry => entry.source.provider !== 'github-release')
    .map(unsupportedProviderMessage)
  if (unsupported.length > 0) {
    throw new HydrationError(unsupported.join('\n'))
  }
  if (pending.length === 0) {
    console.log(
      JSON.stringify({
        status: 'complete',
        hydrated: [],
        alreadyHydrated,
      })
    )
    return
  }
  const repository = await resolveGithubRepository(repositoryRoot)
  const releaseCache = new Map()
  const hydrated = []
  for (const entry of pending) {
    await materializeReleaseEntry(
      repositoryRoot,
      repository,
      entry,
      inspected.get(entry.path),
      releaseCache
    )
    hydrated.push(entry.path)
  }
  console.log(
    JSON.stringify({
      status: 'complete',
      hydrated,
      alreadyHydrated,
    })
  )
}

await main().catch(error => {
  const message =
    error instanceof Error ? error.message : 'Unknown Cheap LFS helper failure.'
  console.error('Cheap LFS hydration stopped: ' + message)
  process.exitCode = 1
})
