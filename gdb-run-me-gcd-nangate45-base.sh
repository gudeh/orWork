source vars-gcd-nangate45-base.sh

cat > gdb_commands.gdb << EOL
break nesterovDbCbk::inDbInstSwapMasterAfter
break nesterovDbCbk::inDbPostMoveInst
run
EOL

gdb --command=gdb_commands.gdb --args openroad -no_init "${SCRIPTS_DIR}/global_place.tcl" -gui

rm gdb_commands.gdb
