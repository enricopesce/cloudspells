# Stato di sviluppo dei componenti CloudSpells

CloudSpells consegna architetture OCI per casi d’uso standard. L’utente fornisce le decisioni che appartengono al suo contesto, come l’immagine applicativa, il dominio o le identità autorizzate. Lo spell si prende carico di scegliere e collegare le risorse, configurare la rete e tradurre le autorizzazioni in policy coerenti con il caso d’uso. Le [regole di progettazione](../AGENTS.md#design-rules) definiscono questo confine.

Il primo percorso da preparare per la beta è **un servizio web scalabile su OCI con `Vcn` e `ScalableWorkload`**. Prima serve correggere la composizione della rete e l’isolamento tra workload. I componenti di supporto si verificano insieme ai percorsi che li usano. Un test tecnico positivo, come quello di `ObjectStorageBucket`, dimostra che il componente funziona nel perimetro verificato.

## Rete e accesso

| Componente | Perimetro e stato | Sviluppo e verifica |
| --- | --- | --- |
| [`Vcn`](../packages/cloudspells-oci/src/cloudspells/providers/oci/network.py#L240) | **Candidato prioritario.** Consegna una rete a quattro livelli con subnet, gateway, routing e regole di base. Il chiamante fornisce il contesto di indirizzamento. | Eliminare la dipendenza dall’ordine di costruzione quando più spell aggiungono regole. Verificare la rete da sola e con i workload previsti. |
| [`VcnRef`](../packages/cloudspells-oci/src/cloudspells/providers/oci/network.py#L1490) | **Supporto.** Riusa una rete di un altro stack. Lo stack proprietario continua a controllarne le regole. | Definire gli output e le responsabilità dello stack proprietario. Verificare i percorsi dichiarati compatibili, incluso OKE con una rete predisposta. |
| [`Nsg`](../packages/cloudspells-oci/src/cloudspells/providers/oci/nsg.py#L654) | **Supporto.** Traduce ruoli e relazioni in regole. Il chiamante definisce la topologia. Le regole replicate nelle liste di subnet possono ampliare l’accesso oltre le relazioni fra NSG. | Limitare i permessi applicativi ai gruppi previsti. Verificare che il flusso autorizzato funzioni e che workload estranei nella stessa subnet restino isolati. |
| [`VcnFlowLogs`](../packages/cloudspells-oci/src/cloudspells/providers/oci/network_logging.py#L40) | **Funzionalità di rete.** Attiva i log per subnet con retention, anche tramite `Vcn`. Accesso ai log, esportazione e allarmi restano esterni. | Verificare che la rete produca log consultabili. Definire un perimetro più ampio solo se si vuole offrire un caso d’uso di audit. |
| [`Bastion`](../packages/cloudspells-oci/src/cloudspells/providers/oci/bastion.py#L106) | **Caso d’uso parziale.** Crea l’endpoint e limita i client, ma lascia al chiamante i permessi degli operatori e l’accesso ai target. La regola SSH attuale si applica alla subnet privata. | Definire operatori, target e sessione come flusso unico. Verificare accesso autorizzato a un target e isolamento degli altri, con ingress SSH circoscritto. |

## Compute Kubernetes e bilanciamento

| Componente | Perimetro e stato | Sviluppo e verifica |
| --- | --- | --- |
| [`ComputeInstance`](../packages/cloudspells-oci/src/cloudspells/providers/oci/compute.py#L46) | **Supporto.** Crea una VM, la colloca in rete e collega eventuali volumi. Il chiamante configura il sistema operativo, il servizio e il montaggio dei dischi. | Mantenere le chiavi generate stabili tra esecuzioni e preservare gli input Pulumi. Verificare il riuso nelle architetture applicative e la stabilità degli aggiornamenti. |
| [`ScalableWorkload`](../packages/cloudspells-oci/src/cloudspells/providers/oci/autoscale.py#L102) | **Candidato prioritario.** Collega bilanciatore, health check, pool di VM e autoscaling. Il cliente porta l’immagine e la configurazione applicativa. | Risolvere chiavi, TLS, regole di rete e semantica dello scaling relativo pianificato, se resta esposto. Verificare richieste ai backend privati, variazioni di capacità e aggiornamenti ripetibili. |
| [`OkeCluster`](../packages/cloudspells-oci/src/cloudspells/providers/oci/kubernetes.py#L1473) | **Candidato dopo la rete.** Predispone cluster, networking, NSG e pool di nodi. Il cliente porta i workload. | Correggere isolamento e compatibilità con `VcnRef`. Verificare accesso al cluster e deploy di un workload su una rete supportata. |
| [`OkeClusterEnhanced`](../packages/cloudspells-oci/src/cloudspells/providers/oci/kubernetes.py#L1623) | **Variante OKE.** Usa la stessa architettura in modalità Enhanced. Workload Identity e DevOps richiedono configurazione per il caso concreto. | Chiudere i problemi condivisi con OKE. Valutare una ricetta Enhanced specifica, ad esempio un workload che accede a OCI tramite Workload Identity. |
| [`LoadBalancer`](../packages/cloudspells-oci/src/cloudspells/providers/oci/loadbalancer.py#L96) | **Caso d’uso parziale.** Predispone HTTPS, redirect e health check. Il chiamante registra i backend e la procedura documentata per il certificato presuppone che il bilanciatore esista già. | Modellare backend e certificato come input del caso d’uso. Verificare primo deploy, redirect, inoltro e rotazione del certificato. |
| [`InternalLoadBalancer`](../packages/cloudspells-oci/src/cloudspells/providers/oci/loadbalancer.py#L386) | **Caso d’uso parziale.** Predispone listener e backend set privati. Il chiamante registra i target. | Collegare i target e correggere l’ingress per porte backend diverse da 80. Verificare traffico e health check su una porta personalizzata. |

## Storage

| Componente | Perimetro e stato | Sviluppo e verifica |
| --- | --- | --- |
| [`ObjectStorageBucket`](../packages/cloudspells-oci/src/cloudspells/providers/oci/storage.py#L95) | **Supporto con verifica live completata.** Crea un bucket privato Standard con versioning disattivato. Accessi, integrazioni e conservazione dipendono dall’architettura che lo usa. | Riutilizzarlo in ricette con un risultato operativo, per esempio un repository di artefatti con produttori, lettori e conservazione. |
| [`BackupBucket`](../packages/cloudspells-oci/src/cloudspells/providers/oci/storage.py#L182) | **Caso circoscritto.** Configura una destinazione versionata con scadenza. La produzione e il ripristino dei backup restano esterni. La regola attuale non elimina le versioni precedenti. | Definire e verificare la conservazione delle versioni, l’accesso del produttore e un esempio di ripristino. |
| [`DataLakeBucket`](../packages/cloudspells-oci/src/cloudspells/providers/oci/storage.py#L294) | **Caso circoscritto.** Automatizza il passaggio da Standard ad Archive e la successiva scadenza degli oggetti. Ingestione, accessi e query restano esterni. | Presentarlo come storage a più livelli. Verificare durate, prerequisiti IAM e funzionamento delle regole di lifecycle su OCI. |
| [`ArchiveBucket`](../packages/cloudspells-oci/src/cloudspells/providers/oci/storage.py#L421) | **Bloccato.** Combina versioning e retention in modo incompatibile. La regola di conservazione è modificabile. | Scegliere la garanzia di conservazione da offrire, correggere la configurazione e verificare cosa OCI consente di modificare o cancellare durante la retention. |
| [`StaticWebsiteBucket`](../packages/cloudspells-oci/src/cloudspells/providers/oci/storage.py#L530) | **Supporto.** Espone oggetti pubblici. Dominio, TLS, pagina iniziale e distribuzione del sito restano al chiamante. | Mantenere esplicita l’esposizione pubblica. Se si vuole offrire un sito statico, definire e verificare uno spell di distribuzione completo. |

## Identità e GenAI

| Componente | Perimetro e stato | Sviluppo e verifica |
| --- | --- | --- |
| [`ComputeInstancePrincipal`](../packages/cloudspells-oci/src/cloudspells/providers/oci/iam.py#L100) | **Supporto IAM.** Crea gruppo dinamico e policy. Le autorizzazioni personalizzate richiedono frammenti IAM e la selezione riguarda tutte le VM del compartimento. | Correggere la dipendenza della policy dal gruppo. Tradurre gli intenti degli spell applicativi in accessi mirati e verificare quali identità li ricevono. |
| [`OkeNodePrincipal`](../packages/cloudspells-oci/src/cloudspells/providers/oci/iam.py#L229) | **Supporto OKE.** Incorpora permessi operativi, ma include anche istanze estranee a OKE nello stesso compartimento. | Definire l’ambito dei nodi autorizzati, correggere la dipendenza della policy dal gruppo e verificare i permessi nel percorso OKE. |
| [`CompartmentAdminGroup`](../packages/cloudspells-oci/src/cloudspells/providers/oci/iam.py#L337) | **Caso circoscritto.** Delega l’amministrazione di un compartimento a un gruppo. La scelta dei membri appartiene al cliente. | Correggere la dipendenza della policy dal gruppo, documentare l’assegnazione dei membri e verificare che la delega resti confinata al compartimento. |
| [`GenAiAgentRag`](../packages/cloudspells-oci/src/cloudspells/providers/oci/genai_agent_rag.py#L82) | **Candidato bloccato.** Collega documenti, knowledge base, sorgente dati, agente, tool ed endpoint. Il cliente fornisce il corpus. La configurazione dell’indice è incompleta. | Correggere l’indice e definire autorizzazioni e ingestione. Verificare il percorso da un documento a una risposta con citazione. |

## API di supporto e CLI

| Componente | Perimetro e stato | Sviluppo e verifica |
| --- | --- | --- |
| `VolumeSpec` e `NodePoolConfig` | **Descrittori.** Rendono esplicite le decisioni sui volumi e sui pool di nodi. | Verificare vincoli e compatibilità con gli spell che li espongono. Mantenere gli input legati alla capacità richiesta dall’utente. |
| Configurazioni di bilanciamento e scaling | **Descrittori.** Modellano listener, backend, metrica, soglie e pianificazione. | Allineare le opzioni ai comportamenti effettivamente supportati, in particolare certificati e azioni pianificate. |
| Ruoli, tier, porte, builder di regole, `Config`, astrazioni e utility del core | **API di supporto.** Forniscono vocabolario, configurazione, naming, tag e contratti comuni. | Verificare che semplifichino i percorsi pubblici. Le chiavi gestite da `BaseResource` rientrano nel lavoro su Compute e autoscaling. |
| [CLI `cs`](../packages/cloudspells-cli/src/cloudspells/cli/main.py) e [template](../packages/cloudspells-cli/src/cloudspells/cli/templates/__init__.py) | **Canale di adozione in alpha.** Genera progetti e gestisce gli stack. `web-db`, per esempio, configura risorse e regole, ma lascia da predisporre servizi e bilanciamento. | Correggere [la stampa degli output segreti](../packages/cloudspells-cli/src/cloudspells/cli/commands/output.py#L56) e la generazione dei progetti. Verificare i template eseguendoli, a partire dal caso d’uso scelto per la beta. |

## Sequenza di lavoro per la beta

1. **Composizione e isolamento.** Rendere prevedibile la raccolta delle regole tra più spell sulla stessa rete. Verificare sia i flussi necessari sia quelli che devono rimanere bloccati.
2. **Percorso web scalabile.** Risolvere stabilità delle chiavi, configurazione TLS e contratti di scaling. L’utente fornisce immagine e configurazione applicativa. Gli spell collegano il bilanciatore ai backend privati e gestiscono la capacità.
3. **Accettazione.** Eseguire in OCI il percorso documentato, controllare traffico, health check, variazione della capacità, preview senza modifiche, aggiornamento intenzionale e pulizia. Valutare la promozione del percorso con questi risultati disponibili.

Per sviluppare il piano di un componente, partire dalla sua riga e specificare il risultato operativo, gli input che appartengono al cliente, le decisioni che prende lo spell, le dipendenze, le modifiche all’API e le prove di accettazione. Aggiornare qui lo stato quando cambia il perimetro, si chiude un blocco o si ottiene una verifica.

## Verifiche già completate

- **Dipendenze e runtime.** Con Pulumi 3.277.0 e `pulumi-oci` 3.18.0, `make check` è passato su Python 3.12 e tutti i 424 test sono passati anche in un ambiente Python 3.11 pulito. Le wheel di core e OCI dichiarano Python 3.11 come minimo.
- **`ObjectStorageBucket` su OCI.** In `eu-frankfurt-1`, OCI ha confermato accesso privato, classe Standard e versioning disattivato. Le preview dopo creazione e aggiornamento non hanno rilevato modifiche. Un tag di prova è stato aggiornato sul bucket esistente e OCI ha confermato la rimozione finale con HTTP 404. La verifica copre il ciclo di vita del bucket.
