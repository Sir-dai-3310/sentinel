import { useState } from 'react'
import { Upload, Loader, AlertCircle, CheckCircle } from 'lucide-react'
import { useWebSocket } from '../hooks/useWebSocket'

interface AnalysisResult {
  verdict: {
    malicious: boolean
    danger_level: number
    reason: string
    mitre_techniques: string[]
    recommended_actions: string[]
  } | null
  rule_hits: Array<{
    rule_id: string
    rule_name: string
    technique: string
    confidence: number
  }>
  agent_trace: string[]
  skipped_llm: boolean
}

export default function Analysis() {
  const [isAnalyzing, setIsAnalyzing] = useState(false)
  const [result, setResult] = useState<AnalysisResult | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [progress, setProgress] = useState<string>('')

  const wsUrl = import.meta.env.VITE_WS_URL || 'ws://localhost:8000/ws/analysis'

  const { isConnected, sendMessage } = useWebSocket(wsUrl, {
    onMessage: (message) => {
      if (message.type === 'ack') {
        setProgress('Analysis started...')
      } else if (message.type === 'progress') {
        setProgress(`Stage: ${message.data.stage} - ${message.data.status}`)
      } else if (message.type === 'result') {
        setResult(message.data)
        setIsAnalyzing(false)
        setProgress('')
      } else if (message.type === 'error') {
        setError(message.data.error)
        setIsAnalyzing(false)
        setProgress('')
      }
    },
    onError: () => {
      setError('WebSocket connection error')
    },
  })

  const handleFileUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return

    setIsAnalyzing(true)
    setError(null)
    setResult(null)

    try {
      const text = await file.text()
      const log = JSON.parse(text)

      if (!isConnected) {
        throw new Error('WebSocket not connected')
      }

      // Send log via WebSocket for real-time analysis
      sendMessage({
        type: 'log',
        data: { log },
      })
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to analyze log')
      setIsAnalyzing(false)
    }
  }

  return (
    <div className="space-y-8">
      <div>
        <h2 className="text-3xl font-bold mb-2">Log Analysis</h2>
        <p className="text-gray-400">Upload a security log for AI-powered analysis</p>
      </div>

      {/* Connection status */}
      <div className="flex items-center space-x-2 text-sm">
        <div className={`w-2 h-2 rounded-full ${isConnected ? 'bg-green-500' : 'bg-red-500'}`} />
        <span className="text-gray-400">
          {isConnected ? 'Connected to analysis service' : 'Disconnected'}
        </span>
      </div>

      {/* Upload area */}
      <div className="bg-gray-800 rounded-lg p-8 border-2 border-dashed border-gray-600 text-center">
        <Upload className="w-12 h-12 mx-auto mb-4 text-gray-400" />
        <h3 className="text-xl font-medium mb-2">Drop your log file here</h3>
        <p className="text-gray-400 mb-4">
          Supports .json format
        </p>
        <label className="inline-block">
          <input
            type="file"
            className="hidden"
            accept=".json"
            onChange={handleFileUpload}
            disabled={!isConnected || isAnalyzing}
          />
          <span className={`px-6 py-3 rounded-lg cursor-pointer transition-colors ${
            isConnected && !isAnalyzing
              ? 'bg-primary-600 hover:bg-primary-700'
              : 'bg-gray-600 cursor-not-allowed'
          }`}>
            {isAnalyzing ? 'Analyzing...' : 'Browse Files'}
          </span>
        </label>
      </div>

      {/* Error message */}
      {error && (
        <div className="bg-red-500/10 border border-red-500 rounded-lg p-4 flex items-start space-x-3">
          <AlertCircle className="w-5 h-5 text-red-500 flex-shrink-0 mt-0.5" />
          <div>
            <h4 className="font-medium text-red-500">Analysis Error</h4>
            <p className="text-sm text-red-400">{error}</p>
          </div>
        </div>
      )}

      {/* Analysis progress */}
      {isAnalyzing && (
        <div className="bg-gray-800 rounded-lg p-6 border border-gray-700">
          <div className="flex items-center space-x-3 mb-4">
            <Loader className="w-5 h-5 animate-spin text-primary-500" />
            <h3 className="text-lg font-medium">Analyzing...</h3>
          </div>
          {progress && (
            <p className="text-sm text-gray-400">{progress}</p>
          )}
        </div>
      )}

      {/* Results */}
      {result && (
        <div className="bg-gray-800 rounded-lg p-6 border border-gray-700">
          <div className="flex items-center justify-between mb-6">
            <h3 className="text-xl font-bold">Analysis Result</h3>
            {result.verdict && (
              <span
                className={`px-4 py-2 rounded-full font-medium ${
                  result.verdict.malicious
                    ? 'bg-red-500/20 text-red-400'
                    : 'bg-green-500/20 text-green-400'
                }`}
              >
                {result.verdict.malicious ? 'Malicious' : 'Benign'}
              </span>
            )}
          </div>

          {result.verdict && (
            <div className="space-y-4">
              {/* Danger level */}
              <div>
                <p className="text-gray-400 text-sm mb-1">Danger Level</p>
                <div className="flex items-center space-x-3">
                  <div className="flex-1 bg-gray-700 rounded-full h-2">
                    <div
                      className={`h-2 rounded-full ${
                        result.verdict.danger_level > 60
                          ? 'bg-red-500'
                          : result.verdict.danger_level > 30
                          ? 'bg-yellow-500'
                          : 'bg-green-500'
                      }`}
                      style={{ width: `${result.verdict.danger_level}%` }}
                    />
                  </div>
                  <span className="font-bold">{result.verdict.danger_level}/100</span>
                </div>
              </div>

              {/* Reason */}
              <div>
                <p className="text-gray-400 text-sm mb-1">Analysis Reason</p>
                <p className="text-gray-200">{result.verdict.reason}</p>
              </div>

              {/* MITRE techniques */}
              {result.verdict.mitre_techniques.length > 0 && (
                <div>
                  <p className="text-gray-400 text-sm mb-2">MITRE ATT&CK Techniques</p>
                  <div className="flex flex-wrap gap-2">
                    {result.verdict.mitre_techniques.map((technique) => (
                      <span
                        key={technique}
                        className="px-3 py-1 bg-primary-500/20 text-primary-400 rounded-full text-sm"
                      >
                        {technique}
                      </span>
                    ))}
                  </div>
                </div>
              )}

              {/* Rule hits */}
              {result.rule_hits.length > 0 && (
                <div>
                  <p className="text-gray-400 text-sm mb-2">Rule Hits</p>
                  <div className="space-y-2">
                    {result.rule_hits.map((hit) => (
                      <div key={hit.rule_id} className="bg-gray-700/50 rounded p-3">
                        <div className="flex items-center justify-between">
                          <div>
                            <p className="font-medium">{hit.rule_name}</p>
                            <p className="text-sm text-gray-400">{hit.technique}</p>
                          </div>
                          <span className="text-sm font-medium">{hit.confidence}%</span>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Agent trace */}
              <div>
                <p className="text-gray-400 text-sm mb-2">Agent Execution Trace</p>
                <div className="flex items-center space-x-2 text-sm">
                  {result.agent_trace.map((agent, i) => (
                    <div key={i} className="flex items-center">
                      <CheckCircle className="w-4 h-4 text-green-500 mr-1" />
                      <span className="text-gray-300">{agent}</span>
                      {i < result.agent_trace.length - 1 && (
                        <span className="mx-2 text-gray-600">→</span>
                      )}
                    </div>
                  ))}
                </div>
              </div>

              {/* Recommended actions */}
              {result.verdict.recommended_actions.length > 0 && (
                <div>
                  <p className="text-gray-400 text-sm mb-2">Recommended Actions</p>
                  <ul className="list-disc list-inside space-y-1 text-gray-300">
                    {result.verdict.recommended_actions.map((action, i) => (
                      <li key={i}>{action}</li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  )
}
