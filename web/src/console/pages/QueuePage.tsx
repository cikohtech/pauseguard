import { MousePointerClick } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'

import { saveSoundPreference, soundPreference } from '@/console/chime'
import { CaseView } from '@/console/components/CaseView'
import { Queue } from '@/console/components/Queue'
import { useConsoleTitle } from '@/console/title'
import { useQueue } from '@/console/useQueue'
import { cn } from '@/lib/utils'

const wide = () => typeof window !== 'undefined' && window.matchMedia?.('(min-width: 1024px)').matches

// /console and /console/cases/:caseId: the queue (360 px, left) beside the open case. On a
// narrow screen only one of them shows.
export function QueuePage() {
  const { caseId = null } = useParams()
  const navigate = useNavigate()
  const [sound, setSound] = useState(soundPreference)
  const queue = useQueue(sound)
  useConsoleTitle(caseId ? 'Case' : 'Queue')

  // On a desktop, open the top case on the first load so the analyst lands on real work.
  const opened = useRef(false)
  useEffect(() => {
    if (opened.current || !queue.cases) return
    opened.current = true
    if (!caseId && queue.cases.length > 0 && wide()) {
      navigate(`/console/cases/${queue.cases[0].case_id}`, { replace: true })
    }
  }, [queue.cases, caseId, navigate])

  return (
    <div className="grid h-full min-h-0 lg:grid-cols-[360px_minmax(0,1fr)]">
      <aside className={cn('min-h-0 border-r border-border bg-background', caseId && 'hidden lg:block')}>
        <Queue
          queue={queue}
          selectedId={caseId}
          sound={sound}
          onToggleSound={() => {
            saveSoundPreference(!sound)
            setSound(!sound)
          }}
        />
      </aside>
      <div className={cn('min-h-0 bg-background', !caseId && 'hidden lg:block')}>
        {caseId ? (
          <CaseView key={caseId} caseId={caseId} />
        ) : (
          <div className="flex h-full flex-col items-center justify-center gap-2 p-8 text-center text-muted-foreground">
            <MousePointerClick aria-hidden="true" className="size-8" />
            <p className="font-medium text-foreground">Select a case from the queue</p>
            <p className="max-w-sm text-sm">
              New RED and AMBER cases arrive here in real time through Firestore, the moment the customer sees their
              verdict.
            </p>
          </div>
        )}
      </div>
    </div>
  )
}
