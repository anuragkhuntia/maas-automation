#!/usr/bin/env python3
"""CLI interface for MAAS automation"""
import argparse
import json
import logging
import sys
from .controller import Controller

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

log = logging.getLogger("maas_automation")


def main():
    parser = argparse.ArgumentParser(
        description="MAAS Automation SDK - Orchestrate machine lifecycle operations",
        epilog="Examples:\n"
               "  maas-automation -i config.json\n"
               "  maas-automation -i config.json -a commission --hosts node01,node02\n"
               "  maas-automation -i config.json -a deploy --hosts node01\n"
               "  maas-automation -i config.json -a list\n",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        '-i', '--input',
        required=True,
        help='Path to JSON configuration file'
    )
    parser.add_argument(
        '-a', '--action',
        help='Action to perform (overrides config): list, commission, deploy, release, delete, etc.'
    )
    parser.add_argument(
        '--hosts',
        help='Comma-separated list of hostnames to target (e.g., "node01,node02" or "all")'
    )
    parser.add_argument(
        '-v', '--verbose',
        action='store_true',
        help='Enable verbose logging'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Print configuration without executing (not yet implemented)'
    )
    parser.add_argument(
        '--max-retries',
        type=int,
        default=5,
        help='Maximum retries for failed operations (0 = infinite, default: 5)'
    )
    
    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    # Load configuration
    try:
        with open(args.input, 'r') as f:
            cfg = json.load(f)
    except FileNotFoundError:
        log.error(f"Configuration file not found: {args.input}")
        sys.exit(1)
    except json.JSONDecodeError as e:
        log.error(f"Invalid JSON in configuration file: {e}")
        sys.exit(1)

    # Validate required fields
    if 'maas_api_url' not in cfg:
        log.error("Missing 'maas_api_url' in configuration")
        sys.exit(1)
    if 'maas_api_key' not in cfg:
        log.error("Missing 'maas_api_key' in configuration")
        sys.exit(1)

    # Override action if specified on command line
    if args.action:
        cfg['actions'] = [args.action]
        log.debug(f"Action overridden via CLI: {args.action}")

    # Filter machines by hostname if specified
    if args.hosts and args.hosts.lower() != 'all':
        target_hosts = [h.strip().lower() for h in args.hosts.split(',')]
        original_machines = cfg.get('machines', [])
        
        if original_machines:
            filtered_machines = [
                m for m in original_machines 
                if m.get('hostname', '').lower() in target_hosts
            ]
            
            if not filtered_machines:
                log.error(f"No machines found matching hostnames: {args.hosts}")
                log.info(f"Available machines: {', '.join([m.get('hostname', '?') for m in original_machines])}")
                sys.exit(1)
            
            cfg['machines'] = filtered_machines
            log.debug(f"Filtered to {len(filtered_machines)} machine(s): {', '.join([m.get('hostname') for m in filtered_machines])}")

    # Initialize controller
    api_url = cfg['maas_api_url']
    api_key = cfg['maas_api_key']
    
    log.info("=" * 60)
    log.info("MAAS AUTOMATION SDK")
    log.info("=" * 60)
    log.info(f"API URL: {api_url}")
    log.info(f"Actions: {', '.join(cfg.get('actions', []))}")
    if args.hosts:
        log.info(f"Target Hosts: {args.hosts}")
    log.info("")

    try:
        controller = Controller(api_url, api_key, max_retries=args.max_retries)
        
        # Special action: list machines
        if 'list' in cfg.get('actions', []):
            controller.list_machines()
            import os
            os._exit(0)
        
        # Special action: show network info
        if 'show_network' in cfg.get('actions', []):
            controller.show_network_info(cfg)
            import os
            os._exit(0)
        
        system_ids = controller.execute_workflow(cfg)
        
        # Final summary
        log.info("\n" + "=" * 70)
        log.info("WORKFLOW SUMMARY")
        log.info("=" * 70)
        log.info(f"Actions Completed: {', '.join(cfg.get('actions', []))}")
        
        if system_ids:
            log.info(f"\nMachines Processed: {len(system_ids)}")
            for idx, sid in enumerate(system_ids, 1):
                # Get machine details for final summary
                try:
                    machine = controller.client.get_machine(sid)
                    hostname = machine.get('hostname', 'unknown')
                    status = machine.get('status_name', 'unknown')
                    log.info(f"  {idx}. {hostname} ({sid}) - Status: {status}")
                except:
                    log.info(f"  {idx}. {sid}")
        else:
            log.info("No machines processed")
        
        log.info("\n✓ All operations completed successfully!")
        log.info("=" * 70 + "\n")
        
        # Cleanup and force exit
        try:
            controller.client.close()
        except:
            pass
        
        logging.shutdown()
        
        # Force immediate exit (don't wait for threads)
        import os
        os._exit(0)

    except KeyboardInterrupt:
        log.warning("\n\nInterrupted by user")
        logging.shutdown()
        sys.exit(130)
    except Exception as e:
        log.error(f"\n\nWorkflow failed: {e}", exc_info=args.verbose)
        logging.shutdown()
        sys.exit(1)


if __name__ == '__main__':
    main()
