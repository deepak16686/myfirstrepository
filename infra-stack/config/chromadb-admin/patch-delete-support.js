const fs = require('fs')

function read(file) {
  return fs.readFileSync(file, 'utf8')
}

function write(file, content) {
  fs.writeFileSync(file, content)
}

function replaceOrThrow(file, search, replacement) {
  const content = read(file)
  if (!content.includes(search)) {
    throw new Error(`Patch target not found in ${file}`)
  }
  write(file, content.replace(search, replacement))
}

function appendIfMissing(file, marker, insertion) {
  const content = read(file)
  if (content.includes(marker)) {
    return
  }
  write(file, `${content.trimEnd()}\n\n${insertion}\n`)
}

const dbFile = '/app/src/lib/server/db.ts'
appendIfMissing(
  dbFile,
  'export async function deleteRecord(',
  `export async function deleteRecord(
  connectionString: string,
  auth: Auth,
  collectionName: string,
  recordId: string,
  tenant: string,
  database: string
) {
  const client = new ChromaClient({
    path: connectionString,
    auth: formatAuth(auth),
    database: database,
    tenant: tenant,
  })

  const embeddingFunction = new DefaultEmbeddingFunction()
  const collection = await client.getCollection({ name: collectionName, embeddingFunction: embeddingFunction })

  await collection.delete({ ids: [recordId] })
}`
)

const routeFile = '/app/src/app/api/collections/[collectionName]/records/route.ts'
replaceOrThrow(
  routeFile,
  "import { countRecord, fetchRecords, queryRecords, queryRecordsText } from '@/lib/server/db'",
  "import { countRecord, deleteRecord, fetchRecords, queryRecords, queryRecordsText } from '@/lib/server/db'"
)
replaceOrThrow(
  routeFile,
  `function extractPage(request: Request) {
  const url = new URL(request.url)
  const searchParams = new URLSearchParams(url.search)
  return parseInt(searchParams.get('page') || '1', 10)
}
`,
  `export async function DELETE(request: Request, { params }: { params: { collectionName: string } }) {
  const connectionString = extractConnectionString(request)
  const auth = extractAuth(request)
  const tenant = extractTenant(request)
  const database = extractDatabase(request)
  const recordId = await extractRecordId(request)

  if (!recordId) {
    return NextResponse.json(
      {
        error: 'Record id is required.',
      },
      { status: 400 }
    )
  }

  try {
    await deleteRecord(connectionString, auth, params.collectionName, recordId, tenant, database)
    return NextResponse.json({
      deleted: true,
      id: recordId,
    })
  } catch (error) {
    return NextResponse.json(
      {
        error: (error as Error).message,
      },
      { status: 500 }
    )
  }
}

function extractPage(request: Request) {
  const url = new URL(request.url)
  const searchParams = new URLSearchParams(url.search)
  return parseInt(searchParams.get('page') || '1', 10)
}

async function extractRecordId(request: Request) {
  const url = new URL(request.url)
  const searchParams = new URLSearchParams(url.search)
  const queryId = searchParams.get('id')

  if (queryId) {
    return queryId
  }

  try {
    const body = await request.json()
    return typeof body?.id === 'string' ? body.id : ''
  } catch (error) {
    return ''
  }
}
`
)

const queryFile = '/app/src/lib/client/query.ts'
replaceOrThrow(
  queryFile,
  "import { useQuery } from '@tanstack/react-query'",
  "import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'"
)
appendIfMissing(
  queryFile,
  'export function useDeleteCollectionRecord(',
  `export function useDeleteCollectionRecord(config?: AppConfig, collectionName?: string) {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async (recordId: string): Promise<{ deleted: boolean; id: string }> => {
      if (!config?.connectionString || !collectionName) {
        throw new Error('Missing ChromaDB collection configuration')
      }

      const response = await fetch(
        \`/api/collections/\${encodeURIComponent(collectionName)}/records?connectionString=\${config.connectionString}&tenant=\${config.tenant}&database=\${config.database}&id=\${encodeURIComponent(recordId)}\${authParamsString(config)}\`,
        {
          method: 'DELETE',
        }
      )

      if (!response.ok) {
        let message = \`API deleteCollectionRecord returns response code: \${response.status}, message: \${response.statusText}\`
        try {
          const body = (await response.json()) as { error?: string }
          if (body.error) {
            message = body.error
          }
        } catch (error) {}
        throw new Error(message)
      }

      return response.json()
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['collections', collectionName, 'records'] })
    },
  })
}`
)

write(
  '/app/src/components/RecordPage/RecordPanel/RecordTable/index.tsx',
  `import { modals } from '@mantine/modals'
import { Table, Text } from '@mantine/core'

import RecordRowActionMenu from './RecordRowActionMenu'

import styles from './index.module.scss'

import type { Record } from '@/lib/types'
import type { RecordsPage } from '@/lib/types'

const RecordTable = ({
  collectionName,
  withQuery,
  recordsPage,
}: {
  collectionName: string
  withQuery: boolean
  recordsPage: RecordsPage
}) => {
  const openDetailModal = (record: Record) => {
    modals.openContextModal({
      modalId: 'recordDetailModal',
      modal: 'recordDetailModal',
      size: 'xl',
      title: \`ID: \${record.id}\`,
      innerProps: { record },
    })
  }

  return (
    <Table highlightOnHover layout={'fixed'}>
      <Table.Thead>
        <Table.Tr>
          <Table.Th w={'48'}></Table.Th>
          {withQuery && <Table.Th w={'10%'}>Distance</Table.Th>}
          <Table.Th w={'10%'}>ID</Table.Th>
          <Table.Th w={'40%'}>Document</Table.Th>
          <Table.Th w={withQuery ? '20%' : '30%'}>Metadata</Table.Th>
          <Table.Th w={'auto'}>Embedding</Table.Th>
        </Table.Tr>
      </Table.Thead>
      <Table.Tbody>
        {recordsPage?.records.map(record => {
          const embedding = record.embedding?.join(', ') ?? ''

          return (
            <Table.Tr key={record.id} onClick={() => openDetailModal(record)}>
              <Table.Td className={styles.td}>
                <RecordRowActionMenu collectionName={collectionName} recordId={record.id} embedding={embedding} />
              </Table.Td>
              {withQuery && <Table.Td className={styles.td}>{record.distance}</Table.Td>}
              <Table.Td className={styles.td}>
                <Text span size={'sm'}>
                  {record.id}
                </Text>
              </Table.Td>
              <Table.Td className={styles.td}>{record.document}</Table.Td>
              <Table.Td className={styles.td}>{record.metadata ? JSON.stringify(record.metadata) : ''}</Table.Td>
              <Table.Td className={styles.td}>{embedding}</Table.Td>
            </Table.Tr>
          )
        })}
      </Table.Tbody>
    </Table>
  )
}

export default RecordTable
`
)

replaceOrThrow(
  '/app/src/components/RecordPage/RecordPanel/index.tsx',
  '<RecordTable withQuery={!!query} recordsPage={queryResult}></RecordTable>',
  '<RecordTable collectionName={collectionName} withQuery={!!query} recordsPage={queryResult}></RecordTable>'
)

write(
  '/app/src/components/RecordPage/RecordPanel/RecordTable/RecordRowActionMenu/index.tsx',
  `import { useSetAtom } from 'jotai'
import { IconDots, IconTrash } from '@tabler/icons-react'
import { modals } from '@mantine/modals'
import { ActionIcon, Menu, Text } from '@mantine/core'

import { useDeleteCollectionRecord, useGetConfig } from '@/lib/client/query'
import { currentPageAtom, queryAtom } from '@/components/RecordPage/atom'

import type { MouseEvent } from 'react'

const RecordRowActionMenu = ({
  collectionName,
  recordId,
  embedding,
}: {
  collectionName: string
  recordId: string
  embedding: string
}) => {
  const setQuery = useSetAtom(queryAtom)
  const setCurrentPage = useSetAtom(currentPageAtom)
  const { data: config } = useGetConfig()
  const deleteMutation = useDeleteCollectionRecord(config, collectionName)

  const queryMenuItemClicked = (event: MouseEvent<HTMLButtonElement>) => {
    event.stopPropagation()
    setQuery(embedding)
    setCurrentPage(1)
  }

  const deleteMenuItemClicked = (event: MouseEvent<HTMLButtonElement>) => {
    event.stopPropagation()
    modals.openConfirmModal({
      title: 'Delete ChromaDB record',
      children: (
        <Text size="sm">
          Delete record {recordId} from {collectionName}? This removes the template from RAG immediately.
        </Text>
      ),
      labels: { confirm: 'Delete', cancel: 'Cancel' },
      confirmProps: { color: 'red' },
      onConfirm: async () => {
        try {
          await deleteMutation.mutateAsync(recordId)
        } catch (error) {
          modals.open({
            title: 'Delete failed',
            children: (
              <Text size="sm" c="red">
                {(error as Error).message}
              </Text>
            ),
          })
        }
      },
    })
  }

  return (
    <Menu shadow="md" width={220} position={'right'} withArrow>
      <Menu.Target>
        <ActionIcon variant="default" aria-label="Record actions" onClick={event => event.stopPropagation()}>
          <IconDots style={{ width: '70%', height: '70%' }} stroke={1.5} />
        </ActionIcon>
      </Menu.Target>

      <Menu.Dropdown>
        <Menu.Item onClick={queryMenuItemClicked}>Query by this record</Menu.Item>
        <Menu.Divider />
        <Menu.Item
          color="red"
          leftSection={<IconTrash style={{ width: '1rem', height: '1rem' }} stroke={1.5} />}
          disabled={deleteMutation.isPending}
          onClick={deleteMenuItemClicked}
        >
          Delete template
        </Menu.Item>
      </Menu.Dropdown>
    </Menu>
  )
}

export default RecordRowActionMenu
`
)

console.log('Patched ChromaDB Admin source with record delete API and UI action')
