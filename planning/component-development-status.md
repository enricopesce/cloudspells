# Stato di sviluppo dei componenti CloudSpells

CloudSpells consegna architetture OCI per casi d’uso standard. L’utente fornisce le decisioni che appartengono al suo contesto, come l’immagine applicativa, il dominio o le identità autorizzate. Lo spell si prende carico di scegliere e collegare le risorse, configurare la rete e tradurre le autorizzazioni in policy coerenti con il caso d’uso. Le [regole di progettazione](../AGENTS.md#design-rules) definiscono questo confine.

Il primo percorso da preparare per la beta è **un servizio web scalabile su OCI con `Vcn` e `ScalableWorkload`**. La composizione della rete è implementata e verificata con i mock Pulumi. La promozione alla beta richiede ancora le prove in OCI su traffico, isolamento e migrazione dei pool esistenti. I componenti di supporto si verificano insieme ai percorsi che li usano.

## Rete e accesso

| Componente | Perimetro e stato | Sviluppo e verifica |
| --- | --- | --- |
| [`Vcn`](../packages/cloudspells-oci/src/cloudspells/providers/oci/network.py#L275) | **Candidato prioritario.** Consegna una rete a quattro livelli con subnet, gateway, routing e regole di base. Alla prima finalizzazione deduplica le regole di subnet per contenuto, dopo la risoluzione degli input Pulumi. | Registrare le regole esplicite di subnet prima della finalizzazione. Gli spell integrati possono aggiungere i propri NSG anche a subnet già create. Verificare in OCI con due workload sulla stessa rete. |
| [`VcnRef`](../packages/cloudspells-oci/src/cloudspells/providers/oci/network.py#L1508) | **Supporto.** Lo stack proprietario gestisce subnet, routing e liste. Lo stack applicativo può creare i propri NSG nella rete importata. I mock verificano l’export e la reimportazione degli output di `Vcn`. | Verificare in OCI i percorsi con `ScalableWorkload` e OKE, inclusi i permessi e le route della rete di origine. |
| [`Nsg`](../packages/cloudspells-oci/src/cloudspells/providers/oci/nsg.py#L284) | **Supporto.** Traduce ruoli e relazioni in regole applicate ai gruppi coinvolti. Chiamate ripetute a `serves()` riusano le regole già configurate per la stessa porta e destinazione. | Verificare in OCI che il traffico autorizzato raggiunga il gruppo di destinazione e che le risorse estranee nella stessa subnet restino isolate. |
| [`VcnFlowLogs`](../packages/cloudspells-oci/src/cloudspells/providers/oci/network_logging.py#L40) | **Funzionalità di rete.** Attiva i log per subnet con retention, anche tramite `Vcn`. Accesso ai log, esportazione e allarmi restano esterni. | Verificare che la rete produca log consultabili. Definire un perimetro più ampio solo se si vuole offrire un caso d’uso di audit. |
| [`Bastion`](../packages/cloudspells-oci/src/cloudspells/providers/oci/bastion.py#L44) | **Caso d’uso parziale.** Crea l’endpoint e limita i client, ma lascia al chiamante i permessi degli operatori e l’accesso ai target. L’SSH si autorizza per singolo NSG di destinazione e indirizzo privato del Bastion. | Definire operatori, target e sessione come flusso unico. Verificare accesso autorizzato a un target e isolamento degli altri, con ingress SSH circoscritto. |

L’egress della subnet privata consente anche connessioni verso indirizzi interni se la destinazione le accetta. Il supporto IPv6 copre l’assegnazione dei prefissi, mentre routing e policy di base restano IPv4. [Architettura VCN](../docs/reference/vcn-architecture.md)

## Compute Kubernetes e bilanciamento

| Componente | Perimetro e stato | Sviluppo e verifica |
| --- | --- | --- |
| [`ComputeInstance`](../packages/cloudspells-oci/src/cloudspells/providers/oci/compute.py#L46) | **Supporto.** Crea una VM, la colloca in rete e collega eventuali volumi. Il chiamante configura il sistema operativo, il servizio e il montaggio dei dischi. | Mantenere le chiavi generate stabili tra esecuzioni e preservare gli input Pulumi. Verificare il riuso nelle architetture applicative e la stabilità degli aggiornamenti. |
| [`ScalableWorkload`](../packages/cloudspells-oci/src/cloudspells/providers/oci/autoscale.py#L103) | **Candidato prioritario.** Collega bilanciatore, health check, pool di VM e autoscaling. Ogni workload ha un gruppo NSG per il bilanciatore e uno per i backend. Il cliente porta l’immagine e la configurazione applicativa. | Risolvere stabilità delle chiavi, configurazione TLS e semantica dello scaling relativo pianificato. Verificare in OCI richieste e health check, migrazione dei pool e variazioni di capacità. |
| [`OkeCluster`](../packages/cloudspells-oci/src/cloudspells/providers/oci/kubernetes.py#L1229) | **Candidato dopo la rete.** Predispone cluster, networking, NSG e pool di nodi. Il cliente porta i workload. | I mock verificano la composizione con `VcnRef`. Verificare in OCI il bootstrap dei nodi e un Service con le annotazioni NSG. |
| [`OkeClusterEnhanced`](../packages/cloudspells-oci/src/cloudspells/providers/oci/kubernetes.py#L1379) | **Variante OKE.** Usa la stessa architettura in modalità Enhanced. Workload Identity e DevOps richiedono configurazione per il caso concreto. | Chiudere i problemi condivisi con OKE. Valutare una ricetta Enhanced specifica, ad esempio un workload che accede a OCI tramite Workload Identity. |
| [`LoadBalancer`](../packages/cloudspells-oci/src/cloudspells/providers/oci/loadbalancer.py#L136) | **Caso d’uso parziale.** Predispone HTTPS, redirect e health check. Il chiamante registra i backend e la procedura documentata per il certificato presuppone che il bilanciatore esista già. | Modellare backend e certificato come input del caso d’uso. Verificare primo deploy, redirect, inoltro e rotazione del certificato. |
| [`InternalLoadBalancer`](../packages/cloudspells-oci/src/cloudspells/providers/oci/loadbalancer.py#L338) | **Caso d’uso parziale.** Predispone listener e backend set privati. Il chiamante registra i target. | Associare i target allo NSG backend e registrarli nel backend set. Verificare traffico e health check su una porta personalizzata. |

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

1. **Composizione e isolamento.** I test con mock verificano due workload su una VCN finalizzata, con gruppi e porte distinti. In OCI, usare la stessa porta backend per entrambi i pool per verificare l’isolamento per NSG. Ogni bilanciatore deve raggiungere il proprio pool e ottenere health check positivi. L’accesso diretto da una VM estranea nella stessa subnet e gli health check del bilanciatore dell’altro workload devono fallire. [Test di composizione](../tests/test_autoscale.py#L126)
2. **Percorso web scalabile.** Risolvere stabilità delle chiavi, configurazione TLS e contratti di scaling. Sui pool esistenti, associare le VM al nuovo NSG backend o sostituirle a lotti. Rimuovere le aperture di subnet precedenti dopo aver verificato gli health check. [Migrazione dei pool](../docs/tutorials/autoscale.md#upgrade-an-existing-pool)
3. **Accettazione.** Eseguire il percorso documentato in OCI e verificare variazioni di capacità, una preview senza differenze dopo il deploy, un aggiornamento intenzionale e la pulizia finale. Valutare la promozione alla beta sulla base di queste prove.

Per sviluppare il piano di un componente, partire dalla sua riga e specificare il risultato operativo, gli input che appartengono al cliente, le decisioni che prende lo spell, le dipendenze, le modifiche all’API e le prove di accettazione. Aggiornare qui lo stato quando cambia il perimetro, si chiude un blocco o si ottiene una verifica.

## Verifiche già completate

- **Suite corrente.** `make check` è passato su Python 3.12 con 441 test. La copertura è del 96,93% nel report standard, del 95,99% sui soli sorgenti e del 98,40% per `network.py`.
- **Rete e CLI con mock.** Verificati la deduplicazione con input Pulumi, l’export/import tra stack, la suddivisione IPv6, i listener HTTP/HTTPS con le rispettive regole NSG e le operazioni del wizard, inclusi errori e annullamenti. [Test VCN](../tests/test_vcn.py) · [Test ScalableWorkload](../tests/test_autoscale.py) · [Test wizard](../packages/cloudspells-cli/tests/test_wizard_operations.py)
- **Compatibilità Python.** Le wheel di core e OCI dichiarano Python 3.11 come minimo. Nella verifica precedente, tutti i 424 test della suite di allora sono passati in un ambiente Python 3.11 pulito con Pulumi 3.277.0 e `pulumi-oci` 3.18.0.
- **`ObjectStorageBucket` su OCI.** In `eu-frankfurt-1`, OCI ha confermato accesso privato, classe Standard e versioning disattivato. Le preview dopo creazione e aggiornamento non hanno rilevato modifiche. Un tag di prova è stato aggiornato sul bucket esistente e OCI ha confermato la rimozione finale con HTTP 404. La verifica copre il ciclo di vita del bucket.
