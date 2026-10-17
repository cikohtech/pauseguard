import { useState } from 'react'
import { Link } from 'react-router-dom'

import { ActionBar } from '@/console/components/case/ActionBar'
import { AuditTab } from '@/console/components/case/AuditTab'
import { CaseHeader } from '@/console/components/case/CaseHeader'
import { EvidenceTab } from '@/console/components/case/EvidenceTab'
import { IntelTab } from '@/console/components/case/IntelTab'
import { RiskTab } from '@/console/components/case/RiskTab'
import { SummaryTab } from '@/console/components/case/SummaryTab'
import { analystFlags } from '@/console/evidence'
import { useCase } from '@/console/useCase'
import { Icon } from '@/components/icons/Icon'
import { Skeleton } from '@/components/ui/skeleton'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'

const Count = ({ n }: { n: number }) =>
  n > 0 ? (
    <span className="inline-flex h-4 min-w-4 items-center justify-center rounded-full bg-surface-container-highest px-1 text-label-s font-medium text-on-surface-variant tabular-nums">
      {n}
    </span>
  ) : null

// The case view (UI_SPEC Area 2, item 2): header, five tabs, and the sticky action bar.
export function CaseView({ caseId }: { caseId: string }) {
  const { load, reload } = useCase(caseId)
  const [tab, setTab] = useState('summary')

  if (load.status === 'loading') {
    return (
      <div className="flex flex-col gap-4 p-6" aria-busy="true" aria-label="Loading the case">
        <Skeleton className="h-8 w-48" />
        <Skeleton className="h-6 w-2/3" />
        <Skeleton className="h-10 w-full" />
        <Skeleton className="h-64 w-full" />
      </div>
    )
  }
  if (load.status === 'error') {
    return (
      <div className="flex flex-col items-start gap-3 p-8">
        <span className="inline-flex size-12 items-center justify-center rounded-full bg-surface-container text-on-surface-variant">
          <Icon name={load.notFound ? 'search' : 'cloud'} />
        </span>
        <h2 className="text-title-l">{load.notFound ? 'Case not found' : 'This case couldn’t be loaded'}</h2>
        <p className="text-body-m text-on-surface-variant">
          {load.notFound ? 'It may have been cleared by a demo reset.' : 'Check your connection and try again.'}
        </p>
        <Link to="/console" className="ripple -ml-3 inline-flex min-h-10 items-center gap-2 rounded-full px-3 text-label-l font-medium text-primary">
          <Icon name="arrow_back" className="size-[18px]" />
          Back to the queue
        </Link>
      </div>
    )
  }

  const { detail } = load
  const intelCount = (detail.intel?.watchlist_matches.length ?? 0) + (detail.intel?.web_findings.length ?? 0)
  return (
    <div className="@container flex h-full min-h-0 flex-col" data-testid="case-view">
      <div className="min-h-0 flex-1 overflow-y-auto">
        <CaseHeader detail={detail} />
        <Tabs value={tab} onValueChange={setTab} className="px-4 pb-8 sm:px-6">
          <TabsList aria-label="Case details">
            <TabsTrigger value="summary">
              Summary
            </TabsTrigger>
            <TabsTrigger value="evidence">
              Evidence <Count n={analystFlags(detail).length} />
            </TabsTrigger>
            <TabsTrigger value="risk">
              Transaction risk
            </TabsTrigger>
            <TabsTrigger value="intel">
              Intel <Count n={intelCount} />
            </TabsTrigger>
            <TabsTrigger value="audit">
              Audit <Count n={detail.audit.length} />
            </TabsTrigger>
          </TabsList>
          <TabsContent value="summary" className="fade-in pt-5">
            <SummaryTab detail={detail} />
          </TabsContent>
          <TabsContent value="evidence" className="fade-in pt-5">
            <EvidenceTab detail={detail} />
          </TabsContent>
          <TabsContent value="risk" className="fade-in pt-5">
            <RiskTab detail={detail} />
          </TabsContent>
          <TabsContent value="intel" className="fade-in pt-5">
            <IntelTab detail={detail} />
          </TabsContent>
          <TabsContent value="audit" className="fade-in pt-5">
            <AuditTab detail={detail} />
          </TabsContent>
        </Tabs>
      </div>
      <ActionBar detail={detail} onDecided={() => void reload()} />
    </div>
  )
}
